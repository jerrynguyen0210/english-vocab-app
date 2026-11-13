"""Shared low-water refill policy; callers hold the user's account lock."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.models import CommonWordJob, CommonWordQuestion, Word

# Each model call requests twenty questions. Start replenishing at half a batch.
BANK_TARGET = 30
REFILL_THRESHOLD = BANK_TARGET // 2


def available_questions(user_id: UUID) -> Select[CommonWordQuestion]:
    saved = (
        select(Word.id)
        .where(
            Word.user_id == user_id,
            Word.normalised_word == CommonWordQuestion.normalised_word,
        )
        .exists()
    )
    return select(CommonWordQuestion).where(
        CommonWordQuestion.user_id == user_id,
        CommonWordQuestion.learned_at.is_(None),
        ~saved,
    )


def available_count(db: Session, user_id: UUID) -> int:
    return (
        db.scalar(
            select(func.count()).select_from(available_questions(user_id).subquery())
        )
        or 0
    )


def queue_refill(db: Session, user_id: UUID) -> bool:
    """Keep one durable job, preserving live leases and failed-job cooldowns."""
    now = datetime.now(UTC)
    job = db.get(CommonWordJob, user_id)
    if job is None:
        db.add(CommonWordJob(user_id=user_id))
    elif job.failed_at is not None:
        if job.failed_at + timedelta(seconds=60) > now:
            return False
        job.failed_at = None
        job.failure_category = None
        job.attempts = 0
        job.lease_token = None
        job.available_at = now
    return True


def refill_if_low(db: Session, user_id: UUID) -> None:
    if available_count(db, user_id) <= REFILL_THRESHOLD:
        queue_refill(db, user_id)
