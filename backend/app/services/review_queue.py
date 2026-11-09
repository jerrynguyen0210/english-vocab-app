"""User-scoped review queue queries; timestamps are compared as UTC instants."""

import uuid
from datetime import datetime

from sqlalchemy import Select, select

from app.core.time import as_utc, local_day_bounds
from app.models import ReviewState, User, Word


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
