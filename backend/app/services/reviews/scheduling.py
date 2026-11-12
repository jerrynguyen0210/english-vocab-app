"""Spaced-repetition scheduling rules."""

from datetime import datetime, timedelta
from math import ceil

from app.core.time import as_utc
from app.models import ReviewState


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
