import importlib.util
import uuid

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import ReviewAttempt, User, Word


@pytest.fixture
def history():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    with (
        engine.begin() as connection,
        Operations.context(MigrationContext.configure(connection)),
    ):
        for name in [
            "0001_initial",
            "0002_users",
            "0003_words",
            "0004_review_states",
            "0005_review_attempts",
            "0006_user_timezone",
            "0007_auth",
            "0008_account_erasure",
            "0009_user_name",
        ]:
            spec = importlib.util.spec_from_file_location(
                name, f"migrations/versions/{name}.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.upgrade()
    with Session(engine) as session:
        user = User(email="history@example.test", password_hash="test-hash")
        session.add(user)
        session.flush()
        word = Word(user_id=user.id, word="hello", english_explanation="Greeting")
        session.add(word)
        session.commit()
        yield session, word
    engine.dispose()


def make_attempt(word, **overrides):
    values = {
        "word_id": word.id,
        "user_id": word.user_id,
        "typed_answer": " ＨELLO ",
        "result": "correct",
        "time_taken_ms": 1200,
    }
    values.update(overrides)
    return ReviewAttempt(**values)


def test_repeated_attempts_and_defaults(history):
    session, word = history
    attempts = [make_attempt(word), make_attempt(word)]
    session.add_all(attempts)
    session.commit()
    assert attempts[0].id != attempts[1].id
    assert attempts[0].typed_answer == " ＨELLO "
    assert attempts[0].normalised_answer == "hello"
    assert attempts[0].reviewed_at is not None


@pytest.mark.parametrize(
    "values",
    [
        {"user_id": uuid.uuid4()},
        {"word_id": uuid.uuid4()},
        {"result": "maybe"},
        {"time_taken_ms": -1},
    ],
)
def test_invalid_attempt_rejected(history, values):
    session, word = history
    session.add(make_attempt(word, **values))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    "statement",
    ["UPDATE review_attempts SET result = 'incorrect'", "DELETE FROM review_attempts"],
)
def test_direct_sql_cannot_change_history(history, statement):
    session, word = history
    session.add(make_attempt(word))
    session.commit()
    with pytest.raises(IntegrityError, match="append-only"):
        session.execute(text(statement))
    session.rollback()


@pytest.mark.parametrize("action", ["update", "delete"])
def test_orm_cannot_change_history(history, action):
    session, word = history
    attempt = make_attempt(word)
    session.add(attempt)
    session.commit()
    if action == "update":
        attempt.result = "incorrect"
    else:
        session.delete(attempt)
    with pytest.raises(ValueError, match="append-only"):
        session.commit()
    session.rollback()
