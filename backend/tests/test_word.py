import uuid

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import Base
from app.models import User, Word
from app.models.word import normalise_word


@pytest.fixture
def session():
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_defaults_and_normalisation(session):
    owner = User(email="owner@example.test", password_hash="test-hash")
    session.add(owner)
    session.flush()
    word = Word(
        user_id=owner.id, word="  Ｈello\tWORLD  ", english_explanation="Greeting"
    )
    session.add(word)
    session.commit()
    assert isinstance(word.id, uuid.UUID)
    assert word.word == "  Ｈello\tWORLD  "
    assert word.normalised_word == "hello world"
    assert word.created_at is not None
    assert word.example_sentence is None
    word.word = "Straße"
    session.commit()
    session.refresh(word)
    assert word.normalised_word == normalise_word("STRASSE")


def test_duplicates_are_scoped_to_owner(session):
    owners = [
        User(email=f"owner{i}@example.test", password_hash="test-hash")
        for i in range(2)
    ]
    session.add_all(owners)
    session.flush()
    session.add_all(
        [
            Word(user_id=u.id, word="Hello", english_explanation="Greeting")
            for u in owners
        ]
    )
    session.commit()
    session.add(
        Word(user_id=owners[0].id, word=" HELLO ", english_explanation="Greeting")
    )
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


@pytest.mark.parametrize(
    "field,value",
    [("word", "  "), ("english_explanation", " "), ("user_id", uuid.uuid4())],
)
def test_invalid_entries(session, field, value):
    owner = User(email="owner@example.test", password_hash="test-hash")
    session.add(owner)
    session.flush()
    values = {"user_id": owner.id, "word": "hello", "english_explanation": "Greeting"}
    values[field] = value
    session.add(Word(**values))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
