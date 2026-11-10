"""Durable pre-migration snapshots; failure must prevent schema changes."""

import hashlib
import os
import subprocess
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from psycopg.conninfo import make_conninfo
from sqlalchemy.engine import make_url

from app.core.config import Settings


def backup_before_migration(settings: Settings) -> Path:
    directory = settings.migration_backup_dir
    if directory is None or not directory.is_absolute():
        raise RuntimeError("MIGRATION_BACKUP_DIR must be an absolute persistent path")
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Preview/production migrations require PostgreSQL")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    directory.chmod(0o700)
    # Keep passwords out of command arguments, logs, and persisted metadata.
    options = {key: str(value) for key, value in url.query.items()}
    password = options.pop("password", url.password)
    conninfo = make_conninfo(
        **options, host=url.host, port=url.port, user=url.username, dbname=url.database
    )
    environment = dict(os.environ)
    if password is not None:
        environment["PGPASSWORD"] = str(password)
    name = f"pre-migration-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex}.dump"
    archive = directory / name
    fd, temporary = tempfile.mkstemp(prefix=".partial-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as output:
            subprocess.run(
                [
                    "pg_dump",
                    "--dbname",
                    conninfo,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                ],
                env=environment,
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
            )
            output.flush()
            os.fsync(output.fileno())
        subprocess.run(
            ["pg_restore", "--list", temporary],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        with open(temporary, "rb") as source:
            digest = hashlib.file_digest(source, "sha256").hexdigest()
        os.replace(temporary, archive)
        sidecar = archive.with_suffix(".dump.sha256")
        with sidecar.open("x") as output:
            sidecar.chmod(0o600)
            output.write(f"{digest}  {name}\n")
            output.flush()
            os.fsync(output.fileno())
        directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except subprocess.CalledProcessError:
        raise RuntimeError(
            "Pre-migration backup failed; schema changes blocked"
        ) from None
    finally:
        Path(temporary).unlink(missing_ok=True)
    cutoff = (datetime.now(UTC) - timedelta(days=30)).timestamp()
    for old in directory.glob("pre-migration-*.dump"):
        if old != archive and old.stat().st_mtime < cutoff:
            old.unlink()
            old.with_suffix(".dump.sha256").unlink(missing_ok=True)
    print(f"Pre-migration backup verified: {archive}", flush=True)
    return archive
