"""User-scoped review queue queries; timestamps are compared as UTC instants."""

import uuid
from datetime import datetime, timedelta
from math import ceil

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
    return normalise_answer(typed_answer) == normalise_answer(saved_word)


def normalise_answer(value: str) -> str:
    return value.strip().casefold()


def schedule_review(state: ReviewState, correct: bool, now: datetime) -> None:
    now = as_utc(now)
    state.last_reviewed_at = now
    # Binary recall maps to SM-2 grades 4 (correct) and 1 (incorrect).
    repetitions = state.repetitions or 0
    interval = state.interval_days or 0
    ease = state.ease_factor or 2.5
    grade = 4 if correct else 1
    state.ease_factor = max(1.3, ease + 0.1 - (5 - grade) * (0.08 + (5 - grade) * 0.02))
    if correct:
        state.correct_count += 1
        state.level = min(state.level + 1, 7)
        state.interval_days = (
            1
            if repetitions == 0
            else 6
            if repetitions == 1
            else min(36500, ceil(interval * ease))
        )
        state.repetitions = repetitions + 1
        state.due_at = now + timedelta(days=state.interval_days)
    else:
        state.incorrect_count += 1
        state.level = 0
        state.repetitions = 0
        state.interval_days = 0
        # Same-day relearning; subsequent success restarts the SM-2 sequence.
        state.due_at = now + timedelta(minutes=10)


def review_totals(db: Session, user: User, now: datetime) -> dict[str, int]:
    """Non-sensitive totals distinguish an empty bank, nothing due and a cap."""
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
        "daily_remaining": remaining_daily_reviews(db, user, now),
    }
