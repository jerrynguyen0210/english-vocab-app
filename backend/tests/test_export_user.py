import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.export_user import export_user
from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word, WordTopic


@pytest.fixture
def database():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    ids = [uuid4(), uuid4()]
    with Session(engine) as db:
        for i, user_id in enumerate(ids):
            db.add(
                User(
                    id=user_id,
                    email=f"person{i}@example.test",
                    name=f"Person {i}",
                    password_hash=f"never-export-password-{i}",
                    timezone="Australia/Adelaide",
                )
            )
            db.flush()
            word = Word(
                user_id=user_id,
                word=f"café {i}",
                english_explanation=f"explanation {i}",
                example_sentence=None,
            )
            db.add(word)
            db.flush()
            db.add(WordTopic(word_id=word.id, tag=f"topic {i}"))
            db.add(
                ReviewState(
                    word_id=word.id, level=1, correct_count=1, incorrect_count=0
                )
            )
            db.add(
                ReviewAttempt(
                    word_id=word.id,
                    user_id=user_id,
                    typed_answer=word.word,
                    result="correct",
                    time_taken_ms=1234,
                )
            )
            db.add(
                AuthSession(
                    user_id=user_id,
                    access_hash=f"never-export-access-{i}",
                    refresh_hash=f"never-export-refresh-{i}",
                    native=True,
                    access_expires_at=datetime.now(UTC),
                    refresh_expires_at=datetime.now(UTC),
                )
            )
        db.commit()
    yield engine, ids
    engine.dispose()


def test_export_is_complete_isolated_and_contains_no_credentials(database, tmp_path):
    engine, ids = database
    output = tmp_path / "user-data.json"
    export_user(engine, ids[0], output)
    raw = output.read_text()
    data = json.loads(raw)
    assert data["format_version"] == 1
    assert data["account"]["id"] == str(ids[0])
    assert data["account"]["email"] == "person0@example.test"
    assert data["account"]["timezone"] == "Australia/Adelaide"
    assert data["words"][0]["word"] == "café 0"
    assert data["words"][0]["example_sentence"] is None
    assert data["word_topics"] == [
        {"word_id": data["words"][0]["id"], "tag": "topic 0"}
    ]
    assert data["review_states"][0]["ease_factor"] == 2.5
    for collection in ["words", "review_states", "review_attempts", "session_metadata"]:
        assert len(data[collection]) == 1
    assert data["review_states"][0]["word_id"] == data["words"][0]["id"]
    assert data["review_attempts"][0]["time_taken_ms"] == 1234
    assert data["exported_at"].endswith("Z")
    assert data["account"]["created_at"].endswith("Z")
    assert str(ids[1]) not in raw
    assert "person1@example.test" not in raw
    assert "never-export" not in raw
    assert "password_hash" not in data["account"]
    assert "access_hash" not in data["session_metadata"][0]
    assert "refresh_hash" not in data["session_metadata"][0]
    assert output.stat().st_mode & 0o777 == 0o600
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 2
        assert db.scalar(select(func.count()).select_from(User)) == 2


def test_missing_user_and_existing_output_are_safe(database, tmp_path):
    engine, ids = database
    output = tmp_path / "user-data.json"
    with pytest.raises(LookupError):
        export_user(engine, uuid4(), output)
    assert not output.exists()
    output.write_text("preserve existing file")
    with pytest.raises(FileExistsError):
        export_user(engine, ids[0], output)
    assert output.read_text() == "preserve existing file"


def test_account_without_words_can_be_exported(database, tmp_path):
    engine, _ = database
    user_id = uuid4()
    with Session(engine) as db:
        db.add(User(id=user_id, email="empty@example.test", password_hash="test-only"))
        db.commit()
    output = tmp_path / "user-data.json"
    export_user(engine, user_id, output)
    data = json.loads(output.read_text())
    for collection in ["words", "review_states", "review_attempts", "session_metadata"]:
        assert data[collection] == []
