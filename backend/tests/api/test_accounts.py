"""API contracts for accounts."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word

from .helpers import create


def test_timezone_update_is_validated_and_scoped_to_owner(api):
    client, _db, owner, other, _ = api
    response = client.patch(
        "/api/v1/account", headers=owner, json={"timezone": "Australia/Adelaide"}
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Australia/Adelaide"
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.get("/api/v1/auth/me", headers=owner).json()["timezone"]
        == "Australia/Adelaide"
    )

    assert client.get("/api/v1/auth/me", headers=other).json()["timezone"] == "UTC"
    for value in ["Invalid/Timezone", "", "../UTC", None, 123]:
        assert (
            client.patch(
                "/api/v1/account", headers=owner, json={"timezone": value}
            ).status_code
            == 422
        )
    assert client.patch("/api/v1/account", json={"timezone": "UTC"}).status_code == 401
    assert (
        client.get("/api/v1/auth/me", headers=owner).json()["timezone"]
        == "Australia/Adelaide"
    )


def test_timezone_update_changes_local_day_selection_without_rescheduling(
    api, monkeypatch
):
    from datetime import UTC, datetime, timedelta

    from app.models import ReviewState
    from app.services.reviews import service

    client, db, owner, _, _ = api
    now = datetime(2026, 11, 12, 20, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(service, "datetime", Clock)
    word_id = uuid.UUID(create(client, owner).json()["id"])
    word = db.get(Word, word_id)
    word.created_at = now - timedelta(hours=10)
    state = db.get(ReviewState, word_id)
    state.due_at = now + timedelta(hours=6)
    db.commit()
    assert client.get("/api/v1/reviews/summary", headers=owner).json()["due_count"] == 0
    yesterday = "/api/v1/reviews/session?source=time&period=Yesterday"
    assert client.get(yesterday, headers=owner).json() == []
    assert (
        client.patch(
            "/api/v1/account", headers=owner, json={"timezone": "Australia/Adelaide"}
        ).status_code
        == 200
    )
    assert client.get("/api/v1/reviews/summary", headers=owner).json()["due_count"] == 1
    assert client.get(yesterday, headers=owner).json()[0]["word_id"] == str(word_id)
    db.refresh(state)
    assert state.due_at == now + timedelta(hours=6)


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
    with pytest.raises(DBAPIError, match="append-only"):
        db.execute(text("DELETE FROM review_attempts"))
    db.rollback()
    response = client.delete("/api/v1/account", headers=owner)
    assert response.status_code == 204 and response.content == b""
    for model in [User, Word, ReviewState, ReviewAttempt, AuthSession]:
        assert db.scalar(select(func.count()).select_from(model)) == 1
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
