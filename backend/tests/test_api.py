"""Exercise HTTP contracts against migrated tables, including erasure triggers."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word


@pytest.fixture
def api(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/api.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    engine = create_engine(url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        connection.execute("PRAGMA foreign_keys=ON")

    with Session(engine) as db:
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app, base_url="https://testserver") as client:

            def account(email):
                tokens = client.post(
                    "/api/v1/auth/register",
                    headers={"X-Auth-Platform": "native"},
                    json={"email": email, "password": "long test password"},
                ).json()
                return {"Authorization": "Bearer " + tokens["access_token"]}, tokens

            owner, tokens = account("owner@example.com")
            other, _ = account("other@example.com")
            yield client, db, owner, other, tokens
    app.dependency_overrides.clear()
    engine.dispose()
    get_settings.cache_clear()


def create(client, headers, word="Hello"):
    return client.post(
        "/api/v1/words",
        headers=headers,
        json={"word": word, "english_explanation": "A greeting"},
    )


def test_create_queue_submit_and_schedule(api):
    client, db, owner, other, _ = api
    response = create(client, owner)
    assert response.status_code == 201
    word_id = response.json()["id"]
    assert create(client, owner, " ＨELLO ").status_code == 409
    assert create(client, other).status_code == 201
    queue = client.get("/api/v1/reviews/next?limit=10", headers=owner)
    assert queue.status_code == 200
    assert queue.json() == [{"word_id": word_id, "english_explanation": "A greeting"}]
    assert "hello" not in queue.text.lower()
    assert queue.headers["cache-control"] == "no-store"
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": " ＨELLO ", "time_taken_ms": 400},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "correct"
    assert response.json()["correct_word"] == "Hello"
    attempt = db.scalar(select(ReviewAttempt))
    assert attempt.normalised_answer == "hello" and attempt.time_taken_ms == 400
    state = db.get(ReviewState, uuid.UUID(word_id))
    assert state.correct_count == 1 and state.level == 1
    assert client.get("/api/v1/reviews/next", headers=owner).json() == []
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "Hello", "time_taken_ms": 1},
        ).status_code
        == 409
    )
    state.due_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": "", "time_taken_ms": 1},
    )
    assert response.json()["result"] == "incorrect"
    assert response.json()["correct_word"] == "Hello"
    assert state.incorrect_count == 1 and state.level == 0


def test_auth_ownership_and_validation(api):
    client, db, owner, other, _ = api
    word_id = create(client, owner).json()["id"]
    assert create(client, {}).status_code == 401
    assert client.get("/api/v1/reviews/next").status_code == 401
    assert client.delete("/api/v1/account").status_code == 401
    for target in [word_id, str(uuid.uuid4())]:
        assert (
            client.post(
                f"/api/v1/reviews/{target}/answer",
                headers=other,
                json={"typed_answer": "Hello", "time_taken_ms": 2},
            ).status_code
            == 404
        )
    for body in [
        {"word": " ", "english_explanation": "x"},
        {"word": "x", "english_explanation": ""},
        {"word": "x" * 201, "english_explanation": "x"},
    ]:
        assert client.post("/api/v1/words", headers=owner, json=body).status_code == 422
    assert client.get("/api/v1/reviews/next?limit=51", headers=owner).status_code == 422
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "Hello", "time_taken_ms": -1},
        ).status_code
        == 422
    )
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0


def test_account_erases_owned_records_and_revokes_all_sessions(api):
    client, db, owner, other, tokens = api
    word_id = create(client, owner).json()["id"]
    create(client, other, "World")
    client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": "Hello", "time_taken_ms": 3},
    )
    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(text("DELETE FROM review_attempts"))
    db.rollback()
    response = client.delete("/api/v1/account", headers=owner)
    assert response.status_code == 204 and response.content == b""
    assert db.scalar(select(func.count()).select_from(User)) == 1
    assert db.scalar(select(func.count()).select_from(Word)) == 1
    assert db.scalar(select(func.count()).select_from(ReviewState)) == 1
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0
    assert db.scalar(select(func.count()).select_from(AuthSession)) == 1
    assert client.get("/api/v1/auth/me", headers=owner).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other).status_code == 200
    assert (
        client.post(
            "/api/v1/auth/refresh",
            headers={"X-Auth-Platform": "native"},
            json={"refresh_token": tokens["refresh_token"]},
        ).status_code
        == 401
    )


def test_only_versioned_product_routes(api):
    client, *_ = api
    assert client.get("/auth/me").status_code == 404
    schema = client.get("/openapi.json").json()
    for path in schema["paths"]:
        assert path == "/health" or path.startswith("/api/v1/")
    item = schema["components"]["schemas"]["ReviewItem"]["properties"]
    assert set(item) == {"word_id", "english_explanation"}


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"word": "hello"},
        {"english_explanation": "greeting"},
        {"word": None, "english_explanation": "greeting"},
        {"word": "hello", "english_explanation": None},
        {"word": 12, "english_explanation": "greeting"},
        {"word": "hello", "english_explanation": ["greeting"]},
        {"word": "\u3000\t\n", "english_explanation": "greeting"},
        {"word": "hello", "english_explanation": "\u3000\t\n"},
        {"word": "hello", "english_explanation": "x" * 5001},
        {
            "word": "hello",
            "english_explanation": "greeting",
            "user_id": str(uuid.uuid4()),
        },
    ],
)
def test_invalid_word_requests_do_not_write(api, body):
    client, db, owner, _, _ = api
    assert client.post("/api/v1/words", headers=owner, json=body).status_code == 422
    assert db.scalar(select(func.count()).select_from(Word)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewState)) == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"typed_answer": "hello"},
        {"time_taken_ms": 1},
        {"typed_answer": None, "time_taken_ms": 1},
        {"typed_answer": 123, "time_taken_ms": 1},
        {"typed_answer": "x" * 201, "time_taken_ms": 1},
        {"typed_answer": "hello", "time_taken_ms": True},
        {"typed_answer": "hello", "time_taken_ms": "1"},
        {"typed_answer": "hello", "time_taken_ms": 1.5},
        {"typed_answer": "hello", "time_taken_ms": None},
        {"typed_answer": "hello", "time_taken_ms": 2147483648},
        {"typed_answer": "hello", "time_taken_ms": 1, "result": "correct"},
        {"typed_answer": "hello", "time_taken_ms": 1, "user_id": str(uuid.uuid4())},
    ],
)
def test_invalid_answer_requests_do_not_change_progress(api, body):
    client, db, owner, _, _ = api
    word_id = create(client, owner).json()["id"]
    state = db.get(ReviewState, uuid.UUID(word_id))
    due_at = state.due_at
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer", headers=owner, json=body
        ).status_code
        == 422
    )
    db.refresh(state)
    assert state.due_at == due_at and state.correct_count == state.incorrect_count == 0
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0


def test_limits_and_duplicate_rule_preserve_existing_word(api):
    client, db, owner, other, _ = api
    body = {"word": "x" * 200, "english_explanation": "e" * 5000}
    response = client.post("/api/v1/words", headers=owner, json=body)
    assert response.status_code == 201
    word_id = uuid.UUID(response.json()["id"])
    state = db.get(ReviewState, word_id)
    due_at = state.due_at
    assert (
        client.post(
            "/api/v1/words",
            headers=owner,
            json={**body, "word": "X" * 200, "english_explanation": "different"},
        ).status_code
        == 409
    )
    assert db.get(Word, word_id).english_explanation == body["english_explanation"]
    db.refresh(state)
    assert state.due_at == due_at
    assert client.post("/api/v1/words", headers=other, json=body).status_code == 201
    assert len(client.get("/api/v1/reviews/next", headers=owner).json()) == 1
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "X" * 200, "time_taken_ms": 2147483647},
        ).status_code
        == 200
    )


def test_queue_and_submission_isolate_accounts(api):
    client, db, owner, other, _ = api
    owner_id = create(client, owner, "OwnerWord").json()["id"]
    other_id = create(client, other, "OtherWord").json()["id"]
    assert client.get("/api/v1/reviews/next?limit=50", headers=owner).json() == [
        {"word_id": owner_id, "english_explanation": "A greeting"}
    ]
    state = db.get(ReviewState, uuid.UUID(other_id))
    original_due = state.due_at
    response = client.post(
        f"/api/v1/reviews/{other_id}/answer",
        headers=owner,
        json={"typed_answer": "OtherWord", "time_taken_ms": 1},
    )
    assert response.status_code == 404 and "OtherWord" not in response.text
    db.refresh(state)
    assert state.due_at == original_due and state.correct_count == 0
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0
    assert client.get("/api/v1/reviews/next?limit=0", headers=owner).status_code == 422
    assert (
        client.get("/api/v1/reviews/next?limit=abc", headers=owner).status_code == 422
    )
    assert (
        client.post(
            "/api/v1/reviews/not-a-uuid/answer",
            headers=owner,
            json={"typed_answer": "x", "time_taken_ms": 1},
        ).status_code
        == 422
    )
