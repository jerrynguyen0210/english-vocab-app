"""Allow one Common refill generation at a time across worker instances."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text

# A dedicated PostgreSQL advisory-lock namespace for Common question generation.
LOCK_NAMESPACE = 1129270605
LOCK_ID = 1


@contextmanager
def generation_slot(engine: Engine) -> Iterator[bool]:
    if engine.dialect.name == "postgresql":
        with engine.connect() as connection:
            acquired = bool(
                connection.scalar(
                    text("SELECT pg_try_advisory_lock(:namespace, :lock_id)"),
                    {"namespace": LOCK_NAMESPACE, "lock_id": LOCK_ID},
                )
            )
            # The session lock survives commit; keep no transaction open during LLM work.
            try:
                connection.commit()
                yield acquired
            finally:
                if acquired:
                    try:
                        connection.execute(
                            text("SELECT pg_advisory_unlock(:namespace, :lock_id)"),
                            {"namespace": LOCK_NAMESPACE, "lock_id": LOCK_ID},
                        )
                        connection.commit()
                    except BaseException:
                        # Never return a connection holding the lock to the pool.
                        connection.invalidate()
                        raise
    elif engine.dialect.name == "sqlite":
        # Local SQLite workers share an OS lock, released automatically after a crash.
        import fcntl

        database = engine.url.database
        if not database or database == ":memory:":
            raise ValueError("Common refill workers require a file-backed database")
        with open(f"{database}.common-refill.lock", "a") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
            else:
                try:
                    yield True
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
    else:
        raise ValueError("Unsupported Common refill worker database")
