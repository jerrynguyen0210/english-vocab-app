from datetime import UTC, datetime, timedelta, timezone

import pytest

from app.models import ReviewState
from app.services.review_queue import answer_matches, normalise_answer, schedule_review


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  HeLLo\n", "hello"),
        ("take  a break", "take  a break"),
        ("Hello!", "hello!"),
        ("ＣＡＴ", "ｃａｔ"),
        ("café", "café"),
        ("  ", ""),
    ],
)
def test_answer_normalisation(value, expected):
    assert normalise_answer(value) == expected


@pytest.mark.parametrize(
    ("answer", "word", "correct"),
    [
        (" HELLO ", "Hello", True),
        ("hello!", "Hello", False),
        ("cafe", "café", False),
        ("take  off", "take off", False),
        ("helo", "hello", False),
        ("", "Hello", False),
    ],
)
def test_checking(answer, word, correct):
    assert answer_matches(answer, word) is correct


@pytest.mark.parametrize(
    ("repetitions", "interval", "ease", "days"),
    [(0, 0, 2.5, 1), (1, 1, 2.5, 6), (2, 6, 2.5, 15), (3, 15, 2.5, 38), (2, 6, 1.3, 8)],
)
def test_correct_schedule(repetitions, interval, ease, days):
    now = datetime(2026, 11, 10, 10, tzinfo=UTC)
    state = ReviewState(
        level=2,
        repetitions=repetitions,
        interval_days=interval,
        ease_factor=ease,
        correct_count=2,
        incorrect_count=3,
    )
    schedule_review(state, True, now)
    assert state.repetitions == repetitions + 1
    assert state.interval_days == days
    assert state.due_at == now + timedelta(days=days)
    assert state.ease_factor == pytest.approx(ease)
    assert state.last_reviewed_at == now
    assert (state.correct_count, state.incorrect_count) == (3, 3)


def test_incorrect_uses_server_instant_across_timezone():
    now = datetime(2026, 11, 10, 23, 55, tzinfo=timezone(timedelta(hours=10)))
    state = ReviewState(
        level=7,
        repetitions=4,
        interval_days=38,
        ease_factor=2.5,
        correct_count=2,
        incorrect_count=3,
    )
    schedule_review(state, False, now)
    assert state.level == 0
    assert state.due_at == now.astimezone(UTC) + timedelta(minutes=10)
    assert state.due_at.tzinfo is UTC
    assert (state.correct_count, state.incorrect_count) == (2, 4)


def test_failure_reduces_ease_then_restarts_and_clamps():
    now = datetime(2026, 11, 10, 10, tzinfo=UTC)
    state = ReviewState(
        level=7,
        repetitions=4,
        interval_days=38,
        ease_factor=2.5,
        correct_count=2,
        incorrect_count=3,
    )
    schedule_review(state, False, now)
    assert state.repetitions == 0 and state.interval_days == 0
    assert state.ease_factor == pytest.approx(1.96)
    schedule_review(state, False, now)
    schedule_review(state, False, now)
    assert state.ease_factor == 1.3
    schedule_review(state, True, now)
    assert state.interval_days == 1 and state.repetitions == 1
