"""Operator-only prompt queue monitoring and explicit retry of failed jobs."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import PromptJob


def queue_status(db: Session) -> dict[str, object]:
    now = datetime.now(UTC)
    pending = PromptJob.failed_at.is_(None) & (PromptJob.available_at <= now)
    in_flight = (
        PromptJob.failed_at.is_(None)
        & PromptJob.lease_token.is_not(None)
        & (PromptJob.available_at > now)
    )
    waiting = (
        PromptJob.failed_at.is_(None)
        & PromptJob.lease_token.is_(None)
        & (PromptJob.available_at > now)
    )
    counts = db.execute(
        select(
            func.count().filter(pending),
            func.count().filter(in_flight),
            func.count().filter(waiting),
            func.count().filter(PromptJob.failed_at.is_not(None)),
            func.min(PromptJob.available_at).filter(pending),
        )
    ).one()
    failures = db.execute(
        select(
            PromptJob.word_id,
            PromptJob.attempts,
            PromptJob.failure_category,
            PromptJob.failed_at,
        )
        .where(PromptJob.failed_at.is_not(None))
        .order_by(PromptJob.failed_at, PromptJob.word_id)
        .limit(20)
    ).mappings()
    return {
        "pending": counts[0],
        "in_flight": counts[1],
        "waiting_retry": counts[2],
        "failed": counts[3],
        "oldest_pending_at": counts[4],
        "failures": [dict(row) for row in failures],
    }


def retry_failed_job(db: Session, word_id: uuid.UUID) -> None:
    reset = db.execute(
        update(PromptJob)
        .where(PromptJob.word_id == word_id, PromptJob.failed_at.is_not(None))
        .values(
            failed_at=None,
            failure_category=None,
            lease_token=None,
            attempts=0,
            available_at=datetime.now(UTC),
        )
        .returning(PromptJob.word_id)
    ).scalar_one_or_none()
    if reset is None:
        raise LookupError("Failed prompt job not found")
    db.commit()
