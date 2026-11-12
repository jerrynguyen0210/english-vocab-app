"""API versioning, authentication, and ownership contracts."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import AuthSession, ReviewAttempt, User, Word


def test_only_versioned_product_routes(api):
    client, *_ = api
    assert client.get("/auth/me").status_code == 404
    schema = client.get("/openapi.json").json()
    for path in schema["paths"]:
        assert path == "/health" or path.startswith("/api/v1/")
    item = schema["components"]["schemas"]["ReviewItem"]["properties"]
    assert set(item) == {"word_id", "english_explanation", "example_sentence"}


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
