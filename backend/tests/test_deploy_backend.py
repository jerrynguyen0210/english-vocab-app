"""Check deployment ordering and failure handling without running Docker."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def deployment(tmp_path, monkeypatch):
    root = tmp_path / "repository"
    (root / "devops").mkdir(parents=True)
    (root / "backend").mkdir()
    script = root / "devops/deploy_backend.sh"
    shutil.copyfile(
        Path(__file__).resolve().parents[2] / "devops/deploy_backend.sh", script
    )
    (root / "backend/.env").write_text(
        "APP_ENVIRONMENT=test\nSECRET_KEY=test-only-placeholder\n"
    )
    (root / "backend/docker-compose.yml").write_text("services: {}\n")
    commands = tmp_path / "commands.jsonl"
    binary = tmp_path / "bin"
    binary.mkdir()
    docker = binary / "docker"
    docker.write_text("""#!/usr/bin/env python3
import json
import os
import sys

arguments = sys.argv[1:]
if arguments == ["compose", "version"]:
    sys.exit(0)
assert arguments[0] == "compose"
assert arguments[1] == "--project-directory" and arguments[3] == "-f"
operation = arguments[5:]
with open(os.environ["MOCK_DOCKER_LOG"], "a") as output:
    output.write(json.dumps(operation) + "\\n")
failure = os.environ.get("MOCK_DOCKER_FAIL")
if operation[0] == failure or (failure == "up:api" and operation[0] == "up" and operation[-1] == "api"):
    sys.exit(1)
""")
    docker.chmod(0o755)
    monkeypatch.setenv("PATH", str(binary) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("MOCK_DOCKER_LOG", str(commands))

    def run(action, failure=None):
        if failure:
            monkeypatch.setenv("MOCK_DOCKER_FAIL", failure)
        result = subprocess.run(
            ["bash", str(script), action],
            cwd=tmp_path,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
        calls = [json.loads(line) for line in commands.read_text().splitlines()]
        return result, calls

    return run


@pytest.mark.parametrize(
    "action,expected",
    [
        ("build", ["build", "api", "prompt-worker", "embedding-worker"]),
        (
            "rebuild",
            [
                "build",
                "--no-cache",
                "--pull",
                "api",
                "prompt-worker",
                "embedding-worker",
            ],
        ),
        (
            "logs",
            [
                "logs",
                "--tail",
                "100",
                "--follow",
                "api",
                "prompt-worker",
                "embedding-worker",
            ],
        ),
        (
            "queue-status",
            ["exec", "-T", "api", "python", "-m", "app.prompt_jobs", "status"],
        ),
    ],
)
def test_commands_include_current_worker_and_queue_tools(deployment, action, expected):
    result, calls = deployment(action)
    assert result.returncode == 0, result.stderr
    assert calls == [expected]


def test_start_builds_both_and_waits_for_migrations_before_starting_worker(deployment):
    result, calls = deployment("start")
    assert result.returncode == 0, result.stderr
    assert calls == [
        ["build", "api", "prompt-worker", "embedding-worker"],
        ["up", "-d", "--wait", "--wait-timeout", "120", "db"],
        ["stop", "prompt-worker", "embedding-worker"],
        [
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "120",
            "api",
        ],
        ["exec", "-T", "api", "python", "-"],
        [
            "up",
            "-d",
            "--no-deps",
            "--force-recreate",
            "--wait",
            "--wait-timeout",
            "120",
            "prompt-worker",
            "embedding-worker",
        ],
        ["ps", "db", "api", "prompt-worker", "embedding-worker"],
    ]


@pytest.mark.parametrize("failure", ["build", "up:api", "exec"])
def test_start_never_starts_worker_after_build_or_api_failure(deployment, failure):
    result, calls = deployment("start", failure)
    assert result.returncode != 0
    assert not any(call[0] == "up" and "embedding-worker" in call for call in calls)
    if failure == "build":
        assert calls == [["build", "api", "prompt-worker", "embedding-worker"]]
    if failure == "exec":
        assert "Background workers remain stopped" in result.stderr
