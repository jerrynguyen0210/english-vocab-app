"""Exercise HTTP contracts against migrated tables, including erasure triggers."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.main import app
from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word
from app.models.word import normalise_word


@pytest.fixture
def api(api_database_url, monkeypatch):
    url = api_database_url
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    command.upgrade(Config("alembic.ini"), "head")
    sqlite = url.startswith("sqlite:")
    engine = create_engine(url, connect_args={"check_same_thread": False} if sqlite else {})

    @event.listens_for(engine, "connect")
    def foreign_keys(connection, _):
        if sqlite:
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


def test_search_marks_only_the_current_users_saved_forms(api):
    client, db, owner, other, _ = api
    assert create(client, owner, " ＣREATE ").status_code == 201
    assert create(client, other, "created").status_code == 201
    response = client.get("/api/v1/words/search?q=create", headers=owner)
    assert response.status_code == 200
    entries = {entry["word"]: entry for entry in response.json()}
    assert entries["create"]["saved"] is True
    assert entries["created"]["saved"] is False
    other_entries = {
        entry["word"]: entry
        for entry in client.get(
            "/api/v1/words/search?q=create",
            headers=other,
        ).json()
    }
    assert other_entries["create"]["saved"] is False
    assert other_entries["created"]["saved"] is True
    assert create(client, owner, "create").status_code == 409
    assert (
        db.scalar(
            select(func.count())
            .select_from(Word)
            .where(
                Word.user_id
                == db.scalar(select(User.id).where(User.email == "owner@example.com")),
            )
        )
        == 1
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
    assert queue.json() == [
        {
            "word_id": word_id,
            "english_explanation": "A greeting",
            "example_sentence": None,
        }
    ]
    assert "hello" not in queue.text.lower()
    assert queue.headers["cache-control"] == "no-store"
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": " HELLO ", "time_taken_ms": 400},
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
    with pytest.raises(DBAPIError, match="append-only"):
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
    assert set(item) == {"word_id", "english_explanation", "example_sentence"}


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
        {
            "word_id": owner_id,
            "english_explanation": "A greeting",
            "example_sentence": None,
        }
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


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("GET", "/api/v1/auth/me", None),
        ("POST", "/api/v1/words", {"word": "Secret", "english_explanation": "Hidden"}),
        ("GET", "/api/v1/reviews/next", None),
        (
            "POST",
            f"/api/v1/reviews/{uuid.uuid4()}/answer",
            {"typed_answer": "Secret", "time_taken_ms": 1},
        ),
        ("DELETE", "/api/v1/account", None),
    ],
)
@pytest.mark.parametrize("credential", ["missing", "invalid", "expired"])
def test_every_protected_route_rejects_unauthorized_requests(
    api, method, path, body, credential
):
    client, db, owner, _, _ = api
    headers = {}
    if credential == "invalid":
        headers = {"Authorization": "Bearer invalid-token"}
    elif credential == "expired":
        user_id = uuid.UUID(client.get("/api/v1/auth/me", headers=owner).json()["id"])
        for record in db.scalars(
            select(AuthSession).where(AuthSession.user_id == user_id)
        ):
            record.access_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        headers = owner
    response = client.request(method, path, headers=headers, json=body)
    assert response.status_code == 401
    assert db.scalar(select(func.count()).select_from(User)) == 2
    assert db.scalar(select(func.count()).select_from(Word)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0


def test_account_deletion_preserves_other_users_history_and_sessions(api):
    client, db, owner, other, tokens = api
    second_device = client.post(
        "/api/v1/auth/sign-in",
        headers={"X-Auth-Platform": "native"},
        json={"email": "owner@example.com", "password": "long test password"},
    ).json()
    owner_word = create(client, owner, "Owner").json()["id"]
    other_word = create(client, other, "Other").json()["id"]
    for headers, word_id, answer in [
        (owner, owner_word, "Owner"),
        (other, other_word, "Other"),
    ]:
        assert (
            client.post(
                f"/api/v1/reviews/{word_id}/answer",
                headers=headers,
                json={"typed_answer": answer, "time_taken_ms": 10},
            ).status_code
            == 200
        )
    other_identity = client.get("/api/v1/auth/me", headers=other).json()
    other_state = db.get(ReviewState, uuid.UUID(other_word))
    snapshot = (other_state.due_at, other_state.correct_count, other_state.level)
    assert client.delete("/api/v1/account", headers=owner).status_code == 204
    for session in [tokens, second_device]:
        assert (
            client.get(
                "/api/v1/auth/me",
                headers={"Authorization": "Bearer " + session["access_token"]},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/api/v1/auth/refresh",
                headers={"X-Auth-Platform": "native"},
                json={"refresh_token": session["refresh_token"]},
            ).status_code
            == 401
        )
    assert client.get("/api/v1/auth/me", headers=other).json() == other_identity
    db.refresh(other_state)
    assert (
        other_state.due_at,
        other_state.correct_count,
        other_state.level,
    ) == snapshot
    attempts = list(db.scalars(select(ReviewAttempt)))
    assert len(attempts) == 1
    assert str(attempts[0].user_id) == other_identity["id"]
    assert str(attempts[0].word_id) == other_word
    assert attempts[0].typed_answer == "Other"
    assert db.get(Word, uuid.UUID(owner_word)) is None


@pytest.mark.parametrize("sentence", [None, "", "   ", "  She showed resilience.  "])
def test_create_word_optional_sentence(api, sentence):
    client, db, owner, _, _ = api
    response = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "resilience",
            "english_explanation": "Recovery",
            "example_sentence": sentence,
        },
    )
    assert response.status_code == 201
    expected = (sentence.strip() or None) if sentence is not None else None
    assert response.json()["example_sentence"] == expected
    assert db.get(Word, uuid.UUID(response.json()["id"])).example_sentence == expected


@pytest.mark.parametrize("sentence", [123, "x" * 5001])
def test_create_word_invalid_sentence(api, sentence):
    client, _, owner, _, _ = api
    response = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "resilience",
            "english_explanation": "Recovery",
            "example_sentence": sentence,
        },
    )
    assert response.status_code == 422


def test_review_hints_mask_answer_before_serialization(api):
    client, _, owner, _, _ = api
    created = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "resilience",
            "english_explanation": "Resilience means recovering after setbacks.",
            "example_sentence": "Her RESILIENCE showed; resilience matters.",
        },
    )
    assert created.status_code == 201
    response = client.get("/api/v1/reviews/next", headers=owner)
    assert response.status_code == 200
    assert response.json() == [
        {
            "word_id": created.json()["id"],
            "english_explanation": "_____ means recovering after setbacks.",
            "example_sentence": "Her _____ showed; _____ matters.",
        }
    ]
    assert "resilience" not in response.text.lower()


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("  TAKE a break  ", "correct"),
        ("take  a break", "incorrect"),
        ("take a break!", "incorrect"),
        ("take a brek", "incorrect"),
        ("ＴＡＫＥ a break", "incorrect"),
        ("", "incorrect"),
    ],
)
def test_d2_result_is_recorded(api, answer, expected):
    client, db, owner, _, _ = api
    word_id = create(client, owner, "Take a break").json()["id"]
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": answer, "time_taken_ms": 100},
    )
    assert response.status_code == 200
    assert response.json()["result"] == expected
    assert response.json()["correct_word"] == "Take a break"
    attempt = db.scalar(select(ReviewAttempt))
    assert attempt.typed_answer == answer
    assert attempt.result == expected
    assert attempt.time_taken_ms == 100


def test_daily_cap_applies_across_sessions_and_isolates_users(api):
    client, db, owner, other, _ = api
    # Seed 19 persisted attempts; only one more is permitted today.
    word_id = create(client, owner, "First").json()["id"]
    word = db.get(Word, uuid.UUID(word_id))
    for _ in range(19):
        db.add(
            ReviewAttempt(
                word_id=word.id,
                user_id=word.user_id,
                typed_answer="First",
                result="correct",
                reviewed_at=datetime.now(UTC),
                time_taken_ms=1,
            )
        )
    db.commit()
    second = create(client, owner, "Second").json()["id"]
    assert len(client.get("/api/v1/reviews/next?limit=50", headers=owner).json()) == 1
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "wrong", "time_taken_ms": 10},
        ).status_code
        == 200
    )
    assert client.get("/api/v1/reviews/next", headers=owner).json() == []
    blocked = client.post(
        f"/api/v1/reviews/{second}/answer",
        headers=owner,
        json={"typed_answer": "Second", "time_taken_ms": 10},
    )
    assert blocked.status_code == 409
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 20
    assert db.get(ReviewState, uuid.UUID(second)).correct_count == 0
    other_word = create(client, other).json()["id"]
    assert len(client.get("/api/v1/reviews/next", headers=other).json()) == 1
    assert (
        client.post(
            f"/api/v1/reviews/{other_word}/answer",
            headers=other,
            json={"typed_answer": "Hello", "time_taken_ms": 10},
        ).status_code
        == 200
    )


def test_daily_cap_uses_user_local_midnight(api):
    from app.core.time import local_day_bounds
    from app.services.review_queue import remaining_daily_reviews

    client, db, owner, _, _ = api
    word_id = create(client, owner).json()["id"]
    word = db.get(Word, uuid.UUID(word_id))
    user = db.get(User, word.user_id)
    user.timezone = "Australia/Adelaide"
    now = datetime(2026, 11, 10, 14, 0, tzinfo=UTC)
    start, end = local_day_bounds(now, user.timezone)
    for moment in [start - timedelta(microseconds=1), start, end]:
        db.add(
            ReviewAttempt(
                word_id=word.id,
                user_id=user.id,
                typed_answer="Hello",
                result="correct",
                reviewed_at=moment,
                time_taken_ms=1,
            )
        )
    db.commit()
    assert remaining_daily_reviews(db, user, now) == 19
    assert remaining_daily_reviews(db, user, end) == 19


def test_retry_after_lost_response_records_once(api):
    client, db, owner, other, _ = api
    word_id = create(client, owner).json()["id"]
    prompt = client.get("/api/v1/reviews/session", headers=owner).json()[0]
    body = {
        "attempt_id": prompt["attempt_id"],
        "typed_answer": "Hello",
        "time_taken_ms": 12,
    }
    first = client.post(f"/api/v1/reviews/{word_id}/answer", headers=owner, json=body)
    retry = client.post(f"/api/v1/reviews/{word_id}/answer", headers=owner, json=body)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 1
    assert db.get(ReviewState, uuid.UUID(word_id)).correct_count == 1
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={**body, "typed_answer": "changed"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer", headers=other, json=body
        ).status_code
        == 404
    )


def test_session_snapshot_excludes_later_additions(api):
    client, _, owner, _, _ = api
    assert client.get("/api/v1/reviews/session", headers=owner).json() == []
    first = create(client, owner).json()["id"]
    snapshot = client.get("/api/v1/reviews/session", headers=owner).json()
    second = create(client, owner, "Later").json()["id"]
    assert [p["word_id"] for p in snapshot] == [first]
    assert {
        p["word_id"]
        for p in client.get("/api/v1/reviews/session", headers=owner).json()
    } == {first, second}
    assert client.get("/api/v1/reviews/session").status_code == 401


def test_preparation_windows_and_overdue_are_user_local(api, monkeypatch):
    import app.api as api_module
    from app.core.time import local_day_bounds

    client, db, owner, other, _ = api
    now = datetime(2026, 10, 5, 2, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(api_module, "datetime", Clock)
    user = db.scalar(select(User).where(User.email == "owner@example.com"))
    user.timezone = "Australia/Sydney"
    start, end = local_day_bounds(now, user.timezone)
    dates = [
        datetime(2026, 10, 3, 13, 59, tzinfo=UTC),
        datetime(2026, 10, 3, 14, tzinfo=UTC),
        datetime(2026, 10, 4, 12, 59, tzinfo=UTC),
        start,
        now - timedelta(days=7),
        now - timedelta(days=7, seconds=1),
        now - timedelta(days=30),
        now - timedelta(days=30, seconds=1),
    ]
    for index, saved_at in enumerate(dates):
        word = Word(
            user_id=user.id,
            word=f"word{index}",
            english_explanation="Meaning",
            created_at=saved_at,
        )
        db.add(word)
        db.flush()
        db.add(
            ReviewState(
                word_id=word.id,
                due_at=[
                    start - timedelta(seconds=1),
                    start,
                    end - timedelta(seconds=1),
                    end,
                ][index % 4],
            )
        )
    db.commit()
    for params, expected in [
        ({"source": "time", "period": "Yesterday"}, 2),
        ({"source": "time", "period": "Weekly"}, 5),
        ({"source": "time", "period": "Monthly"}, 7),
        ({"source": "recall", "include_overdue": True}, 6),
        ({"source": "recall", "include_overdue": False}, 4),
    ]:
        response = client.get(
            "/api/v1/reviews/preparation", params=params, headers=owner
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "count": expected,
            "matching_count": expected,
            "saved_count": 8,
            "due_count": 6,
            "daily_remaining": get_settings().review_daily_cap,
        }
        assert (
            len(
                client.get(
                    "/api/v1/reviews/session", params=params, headers=owner
                ).json()
            )
            == expected
        )
        assert (
            client.get(
                "/api/v1/reviews/preparation", params=params, headers=other
            ).json()["count"]
            == 0
        )
    assert (
        client.get(
            "/api/v1/reviews/preparation?source=time&period=Tomorrow", headers=owner
        ).status_code
        == 422
    )


def test_time_session_authorizes_not_due_answers(api):
    client, db, owner, other, _ = api
    for word in ["hello", "concise"]:
        response = client.post(
            "/api/v1/words",
            headers=owner,
            json={"word": word, "english_explanation": f"{word} means something"},
        )
        assert response.status_code == 201
        db.get(ReviewState, uuid.UUID(response.json()["id"])).due_at = datetime.now(
            UTC
        ) + timedelta(days=20)
    db.commit()
    query = "?source=time&period=Weekly&answer_mode=choice"
    response = client.get("/api/v1/reviews/preparation" + query, headers=owner)
    assert response.json() == {
        "count": 2,
        "matching_count": 2,
        "saved_count": 2,
        "due_count": 0,
        "daily_remaining": get_settings().review_daily_cap,
    }
    assert response.headers["cache-control"] == "no-store"
    items = client.get("/api/v1/reviews/session" + query, headers=owner).json()
    assert len(items) == 2
    first = items[0]
    word = db.get(Word, uuid.UUID(first["word_id"]))
    assert word.word in first["choices"]
    assert word.word not in first["english_explanation"]
    body = {
        "attempt_id": first["attempt_id"],
        "review_token": first["review_token"],
        "typed_answer": word.word,
        "time_taken_ms": 123,
    }
    path = f"/api/v1/reviews/{first['word_id']}/answer"
    assert client.post(path, headers=other, json=body).status_code == 404
    assert (
        client.post(
            path,
            headers=owner,
            json={**body, "review_token": body["review_token"] + "x"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path,
            headers=owner,
            json={key: value for key, value in body.items() if key != "review_token"},
        ).status_code
        == 409
    )
    result = client.post(path, headers=owner, json=body)
    assert result.status_code == 200, result.text
    assert client.post(path, headers=owner, json=body).status_code == 200
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 1
    assert (
        client.post(
            path, headers=owner, json={**body, "attempt_id": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    assert client.get("/api/v1/reviews/preparation").status_code == 401
    assert client.delete("/api/v1/account", headers=owner).status_code == 204


def test_preparation_daily_allowance_and_four_options_for_small_bank(api, monkeypatch):
    client, _, owner, _, _ = api
    monkeypatch.setattr(get_settings(), "review_daily_cap", 1)
    create(client, owner)
    item = client.get(
        "/api/v1/reviews/session?source=recall&answer_mode=choice", headers=owner
    ).json()[0]
    assert len(item["choices"]) == 4
    assert len({normalise_word(option) for option in item["choices"]}) == 4
    assert sum(normalise_word(option) == "hello" for option in item["choices"]) == 1
    create(client, owner, "bye")
    assert client.get(
        "/api/v1/reviews/preparation?source=recall", headers=owner
    ).json() == {
        "count": 1,
        "matching_count": 2,
        "saved_count": 2,
        "due_count": 2,
        "daily_remaining": 1,
    }
    result = client.post(
        f"/api/v1/reviews/{item['word_id']}/answer",
        headers=owner,
        json={
            "attempt_id": item["attempt_id"],
            "review_token": item["review_token"],
            "typed_answer": "Hello",
            "time_taken_ms": 1,
        },
    )
    assert result.status_code == 200
    assert (
        client.get("/api/v1/reviews/preparation?source=time", headers=owner).json()[
            "count"
        ]
        == 0
    )
    assert client.get("/api/v1/reviews/session?source=time", headers=owner).json() == []


def test_topic_search_is_deferred_and_tags_are_not_accepted(api):
    client, _, owner, _, _ = api
    assert (
        client.post(
            "/api/v1/words",
            headers=owner,
            json={"word": "word", "english_explanation": "meaning", "topics": ["work"]},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/words/topics", headers=owner).status_code == 404
    for endpoint in ["preparation", "session"]:
        assert (
            client.get(
                f"/api/v1/reviews/{endpoint}?source=topic", headers=owner
            ).status_code
            == 422
        )


@pytest.mark.parametrize(
    ("word", "example", "explanation", "expected"),
    [
        (
            "resilience",
            "Her RESILIENCE helped; resilience matters.",
            "Resilience is the ability to recover.",
            "Her _____ helped; _____ matters.",
        ),
        (
            "straße",
            "Try ＳＴＲＡＳＳＥ and Straße.",
            "A road.",
            "Try _____ and _____. ",
        ),
        ("take a break", "We take\na break at noon.", "To pause.", "We _____ at noon."),
        ("hello", None, "A greeting.", "“_____” means: A greeting."),
        (
            "hello",
            "An unrelated sentence.",
            "A greeting.",
            "“_____” means: A greeting.",
        ),
    ],
)
def test_session_provides_masked_cloze_sentence_including_fallback(
    api, word, example, explanation, expected
):
    client, db, owner, _, _ = api
    saved = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": word,
            "english_explanation": explanation,
            "example_sentence": example,
        },
    )
    assert saved.status_code == 201
    response = client.get("/api/v1/reviews/session", headers=owner)
    assert response.status_code == 200
    item = response.json()[0]
    assert item["prompt_sentence"] == expected.strip()
    assert "_____" in item["prompt_sentence"]
    assert normalise_word(word) not in normalise_word(item["prompt_sentence"])
    assert normalise_word(word) not in normalise_word(item["english_explanation"])
    assert "correct_word" not in item and "word" not in item
    assert db.get(Word, uuid.UUID(saved.json()["id"])).example_sentence == example


@pytest.mark.parametrize(
    "typed_answer,expected",
    [
        (" HELLO ", "correct"),
        ("helo", "incorrect"),
        ("hello!", "incorrect"),
        ("ＨＥＬＬＯ", "incorrect"),
    ],
)
def test_typing_session_hides_answer_until_d2_submission(api, typed_answer, expected):
    client, _, owner, _, _ = api
    saved = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "Hello",
            "english_explanation": "Hello is a greeting.",
            "example_sentence": "She said HELLO, then hello again.",
        },
    )
    assert saved.status_code == 201
    response = client.get("/api/v1/reviews/session?answer_mode=typing", headers=owner)
    assert response.status_code == 200
    item = response.json()[0]
    assert "choices" not in item and "word" not in item and "correct_word" not in item
    for key in ["prompt_sentence", "english_explanation", "example_sentence"]:
        assert "hello" not in item[key].casefold()
    assert response.headers["cache-control"] == "no-store"
    answer = client.post(
        f"/api/v1/reviews/{item['word_id']}/answer",
        headers=owner,
        json={
            "attempt_id": item["attempt_id"],
            "review_token": item["review_token"],
            "typed_answer": typed_answer,
            "time_taken_ms": 1,
        },
    )
    assert answer.status_code == 200
    assert answer.json()["result"] == expected
    assert answer.json()["correct_word"] == "Hello"


def test_typing_is_default_and_choice_requires_explicit_authorized_request(api):
    client, db, owner, other, _ = api
    create(client, owner)
    item = client.get("/api/v1/reviews/session", headers=owner).json()[0]
    assert "choices" not in item
    body = {"attempt_id": item["attempt_id"], "review_token": item["review_token"]}
    path = f"/api/v1/reviews/{item['word_id']}/choices"
    assert client.post(path, headers=other, json=body).status_code == 404
    assert (
        client.post(
            path, headers=owner, json={**body, "review_token": "forged"}
        ).status_code
        == 409
    )
    result = client.post(path, headers=owner, json=body)
    assert result.status_code == 200, result.text
    choices = result.json()
    assert len(choices["choices"]) == 4
    assert "Hello" in choices["choices"]
    assert choices["attempt_id"] == item["attempt_id"]
    assert choices["review_token"] == item["review_token"]
    assert choices["prompt_sentence"] == item["prompt_sentence"]
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0
    client.post(
        f"/api/v1/reviews/{item['word_id']}/answer",
        headers=owner,
        json={**body, "typed_answer": "Hello", "time_taken_ms": 1},
    )
    assert client.post(path, headers=owner, json=body).status_code == 409


def test_review_summary_distinguishes_empty_bank_nothing_due_and_cap(api, monkeypatch):
    client, db, owner, other, _ = api
    monkeypatch.setattr(get_settings(), "review_daily_cap", 1)
    response = client.get("/api/v1/reviews/summary", headers=owner)
    assert response.status_code == 200
    assert response.json() == {"saved_count": 0, "due_count": 0, "daily_remaining": 1}
    assert response.headers["cache-control"] == "no-store"
    word_id = create(client, owner).json()["id"]
    assert client.get("/api/v1/reviews/summary", headers=owner).json() == {
        "saved_count": 1,
        "due_count": 1,
        "daily_remaining": 1,
    }
    assert (
        client.get("/api/v1/reviews/summary", headers=other).json()["saved_count"] == 0
    )
    client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": "Hello", "time_taken_ms": 1},
    )
    assert client.get("/api/v1/reviews/summary", headers=owner).json() == {
        "saved_count": 1,
        "due_count": 0,
        "daily_remaining": 0,
    }
    db.get(ReviewState, uuid.UUID(word_id)).due_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    db.commit()
    prep = client.get("/api/v1/reviews/preparation?source=recall", headers=owner).json()
    assert prep == {
        "saved_count": 1,
        "due_count": 1,
        "daily_remaining": 0,
        "matching_count": 1,
        "count": 0,
    }
    assert client.get("/api/v1/reviews/summary").status_code == 401
