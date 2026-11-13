"""Operator-only user data export; no HTTP endpoint or schema changes."""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from sqlalchemy import Engine, create_engine, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.models import (
    AuthSession,
    CommonWordQuestion,
    ReviewAttempt,
    ReviewState,
    User,
    Word,
)


def collect_user_data(db: Session, user_id: UUID) -> dict[str, object]:
    # Explicit field lists prevent new credential/internal columns from silently
    # becoming part of the portable data format.
    account = (
        db.execute(
            select(
                User.id,
                User.name,
                User.email,
                User.auth_provider_id,
                User.timezone,
                User.created_at,
                User.disabled_at,
                User.deleted_at,
            ).where(User.id == user_id)
        )
        .mappings()
        .one_or_none()
    )
    if account is None:
        raise LookupError("User not found; no export created")
    words = db.execute(
        select(
            Word.id,
            Word.user_id,
            Word.word,
            Word.normalised_word,
            Word.english_explanation,
            Word.example_sentence,
            Word.created_at,
        )
        .where(Word.user_id == user_id)
        .order_by(Word.created_at, Word.id)
    ).mappings()
    states = db.execute(
        select(
            ReviewState.word_id,
            ReviewState.level,
            ReviewState.repetitions,
            ReviewState.interval_days,
            ReviewState.ease_factor,
            ReviewState.due_at,
            ReviewState.correct_count,
            ReviewState.incorrect_count,
            ReviewState.last_reviewed_at,
        )
        .join(Word, Word.id == ReviewState.word_id)
        .where(Word.user_id == user_id)
        .order_by(ReviewState.word_id)
    ).mappings()
    attempts = db.execute(
        select(
            ReviewAttempt.id,
            ReviewAttempt.word_id,
            ReviewAttempt.user_id,
            ReviewAttempt.typed_answer,
            ReviewAttempt.normalised_answer,
            ReviewAttempt.result,
            ReviewAttempt.reviewed_at,
            ReviewAttempt.time_taken_ms,
            ReviewAttempt.next_due_at,
        )
        .where(ReviewAttempt.user_id == user_id)
        .order_by(ReviewAttempt.reviewed_at, ReviewAttempt.id)
    ).mappings()
    sessions = db.execute(
        select(
            AuthSession.id,
            AuthSession.native,
            AuthSession.access_expires_at,
            AuthSession.refresh_expires_at,
        )
        .where(AuthSession.user_id == user_id)
        .order_by(AuthSession.id)
    ).mappings()
    return {
        "format_version": 1,
        "exported_at": datetime.now(UTC),
        "account": dict(account),
        "words": [dict(row) for row in words],
        "review_states": [dict(row) for row in states],
        "review_attempts": [dict(row) for row in attempts],
        "session_metadata": [dict(row) for row in sessions],
        "common_word_questions": [
            dict(row)
            for row in db.execute(
                select(
                    CommonWordQuestion.id,
                    CommonWordQuestion.word,
                    CommonWordQuestion.ipa,
                    CommonWordQuestion.part_of_speech,
                    CommonWordQuestion.explanation,
                    CommonWordQuestion.example,
                    CommonWordQuestion.choices,
                    CommonWordQuestion.correct_index,
                    CommonWordQuestion.created_at,
                    CommonWordQuestion.last_presented_at,
                    CommonWordQuestion.learned_at,
                )
                .where(CommonWordQuestion.user_id == user_id)
                .order_by(CommonWordQuestion.created_at, CommonWordQuestion.id)
            ).mappings()
        ],
        "excluded": [
            "password hashes",
            "access/refresh tokens and their hashes",
            "shared IP rate-limit buckets",
            "operational logs and backups",
        ],
    }


def json_value(value: object) -> str:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("Export timestamp must have a timezone")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    raise TypeError(f"Unsupported export value: {type(value).__name__}")


def export_user(engine: Engine, user_id: UUID, output: Path) -> None:
    # One snapshot prevents a concurrent review/deletion producing a mixed export.
    with engine.connect() as connection:
        if connection.dialect.name == "postgresql":
            connection = connection.execution_options(isolation_level="REPEATABLE READ")
        with connection.begin():
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            with Session(bind=connection) as db:
                payload = (
                    json.dumps(
                        collect_user_data(db, user_id),
                        default=json_value,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n"
                )
    # Exclusive creation refuses overwrite and symlinks. Do not emit data to stdout.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True, type=UUID)
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="New JSON file in a private directory outside the repository",
    )
    args = parser.parse_args()
    engine = create_engine(get_settings().database_url, poolclass=NullPool)
    try:
        export_user(engine, args.user_id, args.output)
    except (LookupError, FileExistsError):
        parser.exit(1, "Export failed: user missing or output already exists.\n")
    finally:
        engine.dispose()
    print("User export created. Handle the file as private personal data.")


if __name__ == "__main__":
    main()
