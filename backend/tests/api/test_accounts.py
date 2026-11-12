"""API contracts for accounts."""

import uuid

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError

from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word

from .helpers import create


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
