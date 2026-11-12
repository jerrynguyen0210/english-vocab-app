"""User-scoped review queue queries and totals."""

import uuid
from datetime import datetime

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

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


def review_totals(db: Session, user: User, now: datetime) -> dict[str, int]:
    """Non-sensitive totals distinguish an empty bank and nothing due."""
    return {
        "saved_count": db.scalar(
            select(func.count()).select_from(Word).where(Word.user_id == user.id)
        )
        or 0,
        "due_count": db.scalar(
            select(func.count()).select_from(
                due_today(user, now).order_by(None).subquery()
            )
        )
        or 0,
        # Deprecated compatibility field for older clients; never decreases.
        # Sessions are bounded to 50 items, but daily reviews are unlimited.
        "daily_remaining": 50,
    }
