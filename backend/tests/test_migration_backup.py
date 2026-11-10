import subprocess
from unittest.mock import Mock

import pytest

from app.core.config import Settings, get_settings
from app.migrate import upgrade_database
from app.migration_backup import backup_before_migration


def test_failed_dump_never_publishes_or_prunes(tmp_path, monkeypatch):
    old = tmp_path / "pre-migration-old.dump"
    old.write_bytes(b"previous recovery point")
    settings = Settings(
        database_url="postgresql+psycopg://local:placeholder@localhost/vocab",
        secret_key="test",
        app_environment="production",
        migration_backup_dir=tmp_path,
    )
    monkeypatch.setattr(
        "app.migration_backup.subprocess.run",
        Mock(side_effect=subprocess.CalledProcessError(1, "pg_dump")),
    )
    with pytest.raises(RuntimeError, match="schema changes blocked"):
        backup_before_migration(settings)
    assert list(tmp_path.iterdir()) == [old]


@pytest.mark.parametrize("environment", ["preview", "production"])
@pytest.mark.parametrize("fails", [False, True])
def test_backup_gates_upgrade(tmp_path, monkeypatch, environment, fails):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/deploy.db")
    monkeypatch.setenv("APP_ENVIRONMENT", environment)
    get_settings.cache_clear()
    events = []

    def backup(_):
        events.append("backup")
        if fails:
            raise RuntimeError("backup unavailable")

    monkeypatch.setattr("app.migrate.backup_before_migration", backup)
    monkeypatch.setattr(
        "app.migrate.command.upgrade", lambda *_: events.append("upgrade")
    )
    try:
        if fails:
            with pytest.raises(RuntimeError, match="backup unavailable"):
                upgrade_database()
            assert events == ["backup"]
        else:
            upgrade_database()
            assert events == ["backup", "upgrade"]
    finally:
        get_settings.cache_clear()
