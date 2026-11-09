from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.auth import COOKIE, hasher
from app.core.config import get_settings
from app.core.database import Base, get_session
from app.main import app
from app.models import AuthSession, User


@pytest.fixture
def auth():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        app.dependency_overrides[get_session] = lambda: db
        with TestClient(app, base_url="https://testserver") as client:
            yield client, db
    app.dependency_overrides.clear()
    engine.dispose()


CREDS = {"email": "Learner@example.com", "password": "a long test password"}
NATIVE = {"X-Auth-Platform": "native"}
WEB = {"Origin": "http://localhost:8081"}


def test_native_lifecycle(auth):
    client, db = auth
    response = client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE)
    assert response.status_code == 201
    tokens = response.json()
    user = db.scalar(select(User))
    assert user.email == "learner@example.com"
    assert user.password_hash.startswith("$argon2id$")
    assert hasher.verify(user.password_hash, CREDS["password"])
    record = db.scalar(select(AuthSession))
    assert record.refresh_hash != tokens["refresh_token"]
    header = {"Authorization": "Bearer " + tokens["access_token"]}
    assert client.get("/api/v1/auth/me", headers=header).status_code == 200
    record.access_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/v1/auth/me", headers=header).status_code == 401
    refreshed = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
        headers=NATIVE,
    )
    assert refreshed.status_code == 200
    assert (
        client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=NATIVE,
        ).status_code
        == 401
    )
    new = refreshed.json()
    assert (
        client.post(
            "/api/v1/auth/logout",
            json={"refresh_token": new["refresh_token"]},
            headers=NATIVE,
        ).status_code
        == 204
    )
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + new["access_token"]},
        ).status_code
        == 401
    )


def test_web_cookie_csrf_and_rotation(auth):
    client, _ = auth
    response = client.post("/api/v1/auth/register", json=CREDS, headers=WEB)
    assert response.status_code == 201
    assert "refresh_token" not in response.json()
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "secure" in cookie and "samesite=strict" in cookie
    old = client.cookies.get(COOKIE)
    assert client.post("/api/v1/auth/refresh", json={}).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/refresh", json={}, headers={"Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    response = client.post("/api/v1/auth/refresh", json={}, headers=WEB)
    assert response.status_code == 200
    assert client.cookies.get(COOKIE) != old
    assert client.post("/api/v1/auth/logout", json={}, headers=WEB).status_code == 204
    assert client.cookies.get(COOKIE) is None


def test_credentials_disabled_and_expired_refresh(auth):
    client, db = auth
    assert (
        client.post(
            "/api/v1/auth/register", json={**CREDS, "password": "short"}, headers=NATIVE
        ).status_code
        == 422
    )
    client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE)
    assert (
        client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE).status_code
        == 409
    )
    assert (
        client.post(
            "/api/v1/auth/sign-in",
            json={**CREDS, "password": "wrong long password"},
            headers=NATIVE,
        ).status_code
        == 401
    )
    tokens = client.post("/api/v1/auth/sign-in", json=CREDS, headers=NATIVE).json()
    user = db.scalar(select(User))
    user.disabled_at = datetime.now(UTC)
    db.commit()
    assert (
        client.post("/api/v1/auth/sign-in", json=CREDS, headers=NATIVE).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=NATIVE,
        ).status_code
        == 401
    )
    user.disabled_at = None
    for record in db.scalars(select(AuthSession)):
        record.refresh_expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert (
        client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=NATIVE,
        ).status_code
        == 401
    )


def test_rate_limit_shared_between_auth_routes(auth):
    client, _ = auth
    settings = get_settings()
    previous = settings.auth_rate_limit
    settings.auth_rate_limit = 2
    try:
        for _ in range(2):
            assert (
                client.post("/api/v1/auth/refresh", json={}, headers=NATIVE).status_code
                == 401
            )
        response = client.post("/api/v1/auth/sign-in", json=CREDS, headers=NATIVE)
        assert response.status_code == 429
        assert int(response.headers["retry-after"]) > 0
    finally:
        settings.auth_rate_limit = previous


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"email": "learner@example.com"},
        {"password": "long test password"},
        {"email": "not-an-email", "password": "long test password"},
        {"email": None, "password": "long test password"},
        {"email": "learner@example.com", "password": None},
        {"email": "learner@example.com", "password": "x" * 129},
        {"email": "learner@example.com", "password": 123456789012},
        {**CREDS, "user_id": "someone-else"},
    ],
)
def test_auth_input_validation(auth, body):
    client, db = auth
    for endpoint in ["register", "sign-in"]:
        assert (
            client.post(
                f"/api/v1/auth/{endpoint}", json=body, headers=NATIVE
            ).status_code
            == 422
        )
    assert db.scalar(select(User)) is None


def test_refresh_rejects_invalid_and_unexpected_fields(auth):
    client, _ = auth
    for body in [
        {"refresh_token": "short"},
        {"refresh_token": "x" * 257},
        {"refresh_token": 123},
        {"user_id": "someone-else"},
    ]:
        assert (
            client.post("/api/v1/auth/refresh", json=body, headers=NATIVE).status_code
            == 422
        )
