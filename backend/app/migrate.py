"""Forward-only deployment migrations, serialized across PostgreSQL replicas."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.migration_backup import backup_before_migration

# Stable application-specific PostgreSQL session advisory lock.
MIGRATION_LOCK = 824671935102


def upgrade_database() -> None:
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    if len(ScriptDirectory.from_config(config).get_heads()) != 1:
        raise RuntimeError("Deployment requires exactly one migration head")
    settings = get_settings()
    engine = create_engine(settings.database_url, poolclass=NullPool)
    try:
        with engine.connect() as connection:
            postgres = connection.dialect.name == "postgresql"
            if postgres:
                connection.execute(
                    text("SELECT pg_advisory_lock(:key)"), {"key": MIGRATION_LOCK}
                )
                connection.commit()
            try:
                if settings.app_environment in {"preview", "production"}:
                    backup_before_migration(settings)
                    config.attributes["backup_verified"] = True
                config.attributes["connection"] = connection
                command.upgrade(config, "head")
            finally:
                if postgres:
                    connection.rollback()
                    connection.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": MIGRATION_LOCK}
                    )
                    connection.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    upgrade_database()
