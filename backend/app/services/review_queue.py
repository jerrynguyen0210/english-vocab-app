"""User-scoped review queue queries; timestamps are compared as UTC instants."""

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.time import as_utc, local_day_bounds
from app.models import ReviewAttempt, ReviewState, User, Word


def due_today(user: User, now: datetime) -> Select[ReviewState]:
    """Include overdue and all scheduled reviews before next local midnight."""
    _, end = local_day_bounds(now, user.timezone)
    return (
        select(ReviewState)
        .join(Word, Word.id == ReviewState.word_id)
        .where(Word.user_id == user.id, ReviewState.due_at < end)
        .order_by(ReviewState.due_at, ReviewState.word_id)
    )


def ready_to_review(user_id: uuid.UUID, now: datetime) -> Select[ReviewState]:
    return (
        select(ReviewState)
        .join(Word, Word.id == ReviewState.word_id)
        .where(Word.user_id == user_id, ReviewState.due_at <= as_utc(now))
        .order_by(ReviewState.due_at, ReviewState.word_id)
    )


def remaining_daily_reviews(db: Session, user: User, now: datetime) -> int:
    """Count persisted attempts across devices within the user's local day."""
    start, end = local_day_bounds(now, user.timezone)
    attempts = (
        db.scalar(
            select(func.count())
            .select_from(ReviewAttempt)
            .where(
                ReviewAttempt.user_id == user.id,
                ReviewAttempt.reviewed_at >= start,
                ReviewAttempt.reviewed_at < end,
            )
        )
        or 0
    )
    return max(0, get_settings().review_daily_cap - attempts)


def answer_matches(typed_answer: str, saved_word: str) -> bool:
    """D2: ignore case and outer whitespace, otherwise require exact spelling."""
    return typed_answer.strip().casefold() == saved_word.strip().casefold()
