from datetime import UTC, datetime, timedelta, timezone
from zoneinfo import ZoneInfoNotFoundError

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import StatementError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.core.time import local_day_bounds
from app.models import ReviewState, User, Word
from app.services.review_queue import due_today, ready_to_review


@pytest.mark.parametrize(
    "day,hours",
    [
        (datetime(2026, 3, 8, 12, tzinfo=UTC), 23),
        (datetime(2026, 11, 1, 12, tzinfo=UTC), 25),
    ],
)
def test_daylight_saving_boundaries(day, hours):
    start, end = local_day_bounds(day, "America/New_York")
    assert end - start == timedelta(hours=hours)
    assert start.tzinfo is UTC and end.tzinfo is UTC


def test_timezone_validation():
    with pytest.raises(ZoneInfoNotFoundError):
        User(timezone="Invalid/Zone")
    with pytest.raises(ValueError, match="timezone"):
        local_day_bounds(datetime(2026, 1, 1), "UTC")


def test_utc_storage_and_local_queue():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 11, 10, 12, tzinfo=UTC)
    with Session(engine) as session:
        user = User(
            email="queue@example.test",
            password_hash="test-hash",
            timezone="Australia/Adelaide",
        )
        other = User(email="other@example.test", password_hash="test-hash")
        session.add_all([user, other])
        session.flush()
        _, end = local_day_bounds(now, user.timezone)
        states = []
        for i, due in enumerate(
            [now - timedelta(days=1), now, end - timedelta(seconds=1), end]
        ):
            word = Word(user_id=user.id, word=str(i), english_explanation="Example")
            session.add(word)
            session.flush()
            state = ReviewState(
                word_id=word.id, due_at=due.astimezone(timezone(timedelta(hours=9)))
            )
            session.add(state)
            states.append(state)
        word = Word(user_id=other.id, word="other", english_explanation="Example")
        session.add(word)
        session.flush()
        session.add(ReviewState(word_id=word.id, due_at=now))
        session.commit()
        assert states[1].due_at == now
        assert states[1].due_at.tzinfo is UTC
        assert user.created_at.tzinfo is UTC
        assert list(session.scalars(due_today(user, now))) == states[:3]
        assert list(session.scalars(ready_to_review(user.id, now))) == states[:2]
        user.timezone = "UTC"
        assert len(list(session.scalars(due_today(user, now)))) == 4
        states[0].due_at = datetime(2026, 1, 1)
        with pytest.raises(StatementError, match="timezone"):
            session.commit()
        session.rollback()
    engine.dispose()
