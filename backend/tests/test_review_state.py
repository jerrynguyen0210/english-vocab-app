import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import ReviewState, User, Word


@pytest.fixture
def session_and_word():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        owner = User(email="review@example.test", password_hash="test-hash")
        session.add(owner)
        session.flush()
        word = Word(user_id=owner.id, word="hello", english_explanation="Greeting")
        session.add(word)
        session.commit()
        yield session, word
    engine.dispose()


def test_defaults_and_review_update(session_and_word):
    session, word = session_and_word
    state = ReviewState(word_id=word.id)
    session.add(state)
    session.commit()
    assert state.level == state.correct_count == state.incorrect_count == 0
    assert state.due_at is not None
    assert state.last_reviewed_at is None
    state.level = 1
    state.correct_count = 1
    state.last_reviewed_at = datetime.now(UTC)
    state.due_at = datetime(2030, 1, 1, tzinfo=UTC)
    session.commit()
    session.refresh(state)
    assert state.level == state.correct_count == 1
    assert state.last_reviewed_at is not None
    assert state.due_at.year == 2030


@pytest.mark.parametrize("field", ["level", "correct_count", "incorrect_count"])
def test_negative_progress_rejected(session_and_word, field):
    session, word = session_and_word
    state = ReviewState(word_id=word.id)
    setattr(state, field, -1)
    session.add(state)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_missing_word_rejected(session_and_word):
    session, _ = session_and_word
    session.add(ReviewState(word_id=uuid.uuid4()))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_one_state_per_word_and_deletion(session_and_word):
    session, word = session_and_word
    word_id = word.id
    session.add(ReviewState(word_id=word_id))
    session.commit()
    session.add(ReviewState(word_id=word_id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.delete(word)
    session.commit()
    assert session.get(ReviewState, word_id) is None
