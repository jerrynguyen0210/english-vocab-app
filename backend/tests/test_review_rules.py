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
    ("level", "days"),
    [(0, 1), (1, 2), (2, 4), (3, 7), (4, 14), (5, 30), (6, 60), (7, 60)],
)
def test_correct_schedule(level, days):
    now = datetime(2026, 11, 10, 10, tzinfo=UTC)
    state = ReviewState(level=level, correct_count=2, incorrect_count=3)
    schedule_review(state, True, now)
    assert state.level == min(level + 1, 7)
    assert state.due_at == now + timedelta(days=days)
    assert state.last_reviewed_at == now
    assert (state.correct_count, state.incorrect_count) == (3, 3)


def test_incorrect_uses_server_instant_across_timezone():
    now = datetime(2026, 11, 10, 23, 55, tzinfo=timezone(timedelta(hours=10)))
    state = ReviewState(level=7, correct_count=2, incorrect_count=3)
    schedule_review(state, False, now)
    assert state.level == 0
    assert state.due_at == now.astimezone(UTC) + timedelta(minutes=10)
    assert state.due_at.tzinfo is UTC
    assert (state.correct_count, state.incorrect_count) == (2, 4)
