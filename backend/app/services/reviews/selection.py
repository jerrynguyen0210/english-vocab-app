"""Shared selection for preparation counts and bounded review snapshots."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, select

from app.core.time import local_day_bounds
from app.models import ReviewState, User, Word
from app.schemas.reviews import ReviewSelection


def selected_words(
    user: User, now: datetime, selection: ReviewSelection
) -> Select[Word, ReviewState]:
    if selection.source == "topic":
        raise ValueError("Topic selections must use semantic ranking")
    query = (
        select(Word, ReviewState)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.user_id == user.id)
    )
    start, end = local_day_bounds(now, user.timezone)
    if selection.source == "recall":
        query = query.where(ReviewState.due_at < end)
        if not selection.include_overdue:
            query = query.where(ReviewState.due_at >= start)
        return query.order_by(ReviewState.due_at, Word.id)
    if selection.source == "time":
        if selection.period == "Yesterday":
            yesterday = start.astimezone(ZoneInfo(user.timezone)).date() - timedelta(
                days=1
            )
            lower = datetime.combine(
                yesterday, time.min, tzinfo=ZoneInfo(user.timezone)
            ).astimezone(UTC)
            upper = start
        else:
            lower = now - timedelta(days=7 if selection.period == "Weekly" else 30)
            upper = now
        query = query.where(Word.created_at >= lower, Word.created_at < upper)
    return query.order_by(Word.created_at.desc(), Word.id)
