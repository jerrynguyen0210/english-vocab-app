"""Exercise production release rollback and Compose isolation without deployment."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def publisher(tmp_path, monkeypatch):
    repo = tmp_path / "repository"
    scripts = repo / "devops"
    scripts.mkdir(parents=True)
    for name in ["publish_production_web.sh", "deploy-jetson.sh", "deploy_backend.sh"]:
        shutil.copyfile(REPO / "devops" / name, scripts / name)
    backend = repo / "backend"
    backend.mkdir()
    shutil.copyfile(
        REPO / "backend/docker-compose.jetson.yml",
        backend / "docker-compose.jetson.yml",
    )
    (backend / ".env").write_text(
        "SECRET_KEY=test-only-placeholder\nPOSTGRES_PASSWORD=test-only-placeholder\n"
    )
    build = tmp_path / "export"
    build.mkdir()
    (build / "index.html").write_text("New public SPA")
    root = tmp_path / "releases"
    old = root / "releases/previous"
    old.mkdir(parents=True)
    (old / "index.html").write_text("Previous public SPA")
    (root / "current").symlink_to(old)
    binary = tmp_path / "bin"
    binary.mkdir()
    commands = {
        "sudo": """#!/usr/bin/env python3
import os, sys
if sys.argv[1:] == ["-v"]:
    sys.exit(0)
assert sys.argv[1] in {"nginx", "install", "cp", "chmod", "ln", "mv", "rm"}
os.execvp(sys.argv[1], sys.argv[1:])
""",
        "nginx": "#!/bin/sh\nexit 0\n",
        "uname": "#!/bin/sh\necho aarch64\n",
        "ss": "#!/bin/sh\nexit 0\n",
        "git": "#!/bin/sh\necho abc123\n",
        "curl": """#!/usr/bin/env python3
import os, sys
from pathlib import Path
url = sys.argv[-1]
if "/api/" in url:
    print("502" if os.environ.get("MOCK_BAD_PROXY") else "401", end="")
elif url.endswith("/health"):
    pass
elif os.environ.get("MOCK_BAD_PAGE") and url.endswith("/review-preparation"):
    print("Broken response", end="")
else:
    print((Path(os.environ["MOCK_BUILD"]) / "index.html").read_text(), end="")
""",
        "docker": """#!/usr/bin/env python3
import json, os, sys
args = sys.argv[1:]
if args[0] == "inspect":
    print(os.environ.get("MOCK_CURRENT_VOLUME", "existing-volume"))
    sys.exit(0)
if args == ["compose", "version"]:
    sys.exit(0)
operation = args[5:]
with open(os.environ["MOCK_DOCKER_LOG"], "a") as output:
    output.write(json.dumps(operation) + "\\n")
if operation == ["ps", "-q", "api"]:
    print("existing-managed-api")
elif operation == ["ps", "-a", "-q", "db"]:
    print("existing-managed-db")
elif operation == ["config", "--format", "json"]:
    print(json.dumps({"volumes": {"postgres_data": {"name": "existing-volume"}}}))
if os.environ.get("MOCK_BUILD_FAIL") and operation[0] == "build":
    sys.exit(1)
""",
    }
    for name, content in commands.items():
        command = binary / name
        command.write_text(content)
        command.chmod(0o755)
    log = tmp_path / "docker.jsonl"
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("MOCK_BUILD", str(build))
    monkeypatch.setenv("MOCK_DOCKER_LOG", str(log))

    def run(orchestrate=False):
        name = "deploy-jetson.sh" if orchestrate else "publish_production_web.sh"
        option = "--web-build-dir" if orchestrate else "--build-dir"
        result = subprocess.run(
            [
                "bash",
                str(scripts / name),
                option,
                str(build),
                "--release-root",
                str(root),
                "--skip-public-check",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=15,
        )
        return result

    return run, root, old, build, log


def test_spa_publication_preserves_previous_release(publisher):
    run, root, old, _build, _log = publisher
    result = run()
    assert result.returncode == 0, result.stderr
    assert (root / "current/index.html").read_text() == "New public SPA"
    assert (old / "index.html").read_text() == "Previous public SPA"


def test_failed_route_check_restores_previous_release(publisher, monkeypatch):
    run, root, old, _build, _log = publisher
    monkeypatch.setenv("MOCK_BAD_PAGE", "1")
    assert run().returncode != 0
    assert (root / "current").resolve() == old


def test_bad_api_proxy_prevents_release_switch(publisher, monkeypatch):
    run, root, old, _build, _log = publisher
    monkeypatch.setenv("MOCK_BAD_PROXY", "1")
    assert run().returncode != 0
    assert (root / "current").resolve() == old


def test_export_cannot_contain_source_or_environment_files(publisher):
    run, root, old, build, _log = publisher
    (build / ".env").write_text("test-only-placeholder")
    assert run().returncode != 0
    assert (root / "current").resolve() == old


@pytest.mark.skipif(
    os.geteuid() == 0, reason="Jetson entry point intentionally rejects root"
)
def test_existing_database_volume_must_match_before_deployment(publisher, monkeypatch):
    run, root, old, _build, log = publisher
    monkeypatch.setenv("MOCK_CURRENT_VOLUME", "different-existing-data")
    result = run(orchestrate=True)
    assert result.returncode != 0
    assert "Database storage differs" in result.stderr
    assert (root / "current").resolve() == old
    operations = [json.loads(line) for line in log.read_text().splitlines()]
    assert not any(operation[0] in {"build", "stop", "up"} for operation in operations)


@pytest.mark.skipif(
    os.geteuid() == 0, reason="Jetson entry point intentionally rejects root"
)
@pytest.mark.parametrize("build_fails", [False, True])
def test_jetson_uses_production_backend_and_preserves_site_until_ready(
    publisher, monkeypatch, build_fails
):
    run, root, old, _build, log = publisher
    if build_fails:
        monkeypatch.setenv("MOCK_BUILD_FAIL", "1")
    result = run(orchestrate=True)
    operations = [json.loads(line) for line in log.read_text().splitlines()]
    assert ["build", "api", "prompt-worker"] in operations
    if build_fails:
        assert result.returncode != 0
        assert (root / "current").resolve() == old
        assert ["stop", "prompt-worker"] not in operations
    else:
        assert result.returncode == 0, result.stderr
        assert (root / "current/index.html").read_text() == "New public SPA"
        assert [
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "120",
            "prompt-worker",
        ] in operations


def test_production_compose_preserves_data_namespace_and_removes_dev_exposure(tmp_path):
    if not shutil.which("docker"):
        pytest.skip("Docker Compose parser is unavailable")
    version = subprocess.run(
        ["docker", "compose", "version"], capture_output=True, check=False
    )
    if version.returncode:
        pytest.skip("Docker Compose parser is unavailable")
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / ".env").write_text(
        "POSTGRES_PASSWORD=test-only-placeholder\nSECRET_KEY=test-only-placeholder\n"
    )
    configs = []
    for filename in ["docker-compose.yml", "docker-compose.jetson.yml"]:
        path = backend / filename
        shutil.copyfile(REPO / "backend" / filename, path)
        result = subprocess.run(
            [
                "docker",
                "compose",
                "--project-directory",
                str(backend),
                "-f",
                str(path),
                "config",
                "--format",
                "json",
            ],
            capture_output=True,
            text=True,
            check=True,
            env={
                **os.environ,
                "PUBLIC_DOMAIN": "vocab.jerryitdev.com",
                "API_PORT": "8001",
            },
        )
        configs.append(json.loads(result.stdout))
    development, production = configs
    assert (
        production["volumes"]["postgres_data"]["name"]
        == development["volumes"]["postgres_data"]["name"]
    )
    api = production["services"]["api"]
    assert api["ports"][0]["host_ip"] == "127.0.0.1"
    assert not production["services"]["db"].get("ports")
    assert "--reload" not in api["command"]
    assert all(
        mount["target"] not in {"/app/app", "/app/migrations"}
        for mount in api["volumes"]
    )
    assert api["environment"]["APP_ENVIRONMENT"] == "production"
    assert api["environment"]["AUTH_COOKIE_SECURE"] == "true"
    assert json.loads(api["environment"]["CORS_ORIGINS"]) == [
        "https://vocab.jerryitdev.com"
    ]
