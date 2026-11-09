"""Deployment upgrades are repeatable and errors stop API startup."""

import os
import subprocess

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from app.core.config import get_settings
from app.migrate import upgrade_database


def test_upgrade_and_repeated_run(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/deploy.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "0007")
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :hash)"
                ),
                {
                    "id": "1" * 32,
                    "email": "existing@example.com",
                    "hash": "placeholder-hash",
                },
            )
        engine.dispose()
        upgrade_database()
        upgrade_database()
        engine = create_engine(url)
        with engine.connect() as conn:
            assert (
                conn.scalar(text("SELECT version_num FROM alembic_version")) == "0009"
            )
            assert (
                conn.scalar(
                    text("SELECT name FROM users WHERE email = 'existing@example.com'")
                )
                is None
            )
            conn.execute(
                text(
                    "UPDATE users SET name = 'Alex' WHERE email = 'existing@example.com'"
                )
            )
            assert (
                conn.scalar(
                    text("SELECT name FROM users WHERE email = 'existing@example.com'")
                )
                == "Alex"
            )
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_entrypoint_stops_on_migration_failure(tmp_path):
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\nexit 17\n")
    python.chmod(0o755)
    result = subprocess.run(
        ["sh", "entrypoint.sh", "sh", "-c", "echo API_STARTED"],
        env={**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 17
    assert "API_STARTED" not in result.stdout
