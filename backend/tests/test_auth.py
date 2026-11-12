from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.api.auth_transport import COOKIE
from app.core.config import get_settings
from app.core.database import Base, get_session
from app.main import app
from app.models import AuthSession, User
from app.services.auth import hasher


@pytest.fixture
def auth(api_database_url):
    engine = create_engine(
        api_database_url,
        connect_args={"check_same_thread": False}
        if api_database_url.startswith("sqlite:")
        else {},
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


@pytest.mark.parametrize(
    "authorization", [None, "", "Bearer", "Bearer unknown", "Basic unknown"]
)
def test_missing_or_invalid_bearer_is_unauthorized(auth, authorization):
    client, _ = auth
    headers = {} if authorization is None else {"Authorization": authorization}
    response = client.get("/api/v1/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_unknown_email_and_wrong_password_have_same_response(auth):
    client, _ = auth
    assert (
        client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE).status_code
        == 201
    )
    wrong = client.post(
        "/api/v1/auth/sign-in",
        headers=NATIVE,
        json={**CREDS, "password": "incorrect password"},
    )
    unknown = client.post(
        "/api/v1/auth/sign-in",
        headers=NATIVE,
        json={**CREDS, "email": "unknown@example.com"},
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Invalid email or password"}


def test_refresh_invalidates_old_access_and_preserves_absolute_expiry(auth):
    client, db = auth
    tokens = client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE).json()
    expiry = db.scalar(select(AuthSession)).refresh_expires_at
    response = client.post(
        "/api/v1/auth/refresh",
        headers=NATIVE,
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert response.status_code == 200
    new = response.json()
    assert new["access_token"] != tokens["access_token"]
    assert new["refresh_token"] != tokens["refresh_token"]
    assert db.scalar(select(AuthSession)).refresh_expires_at == expiry
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + tokens["access_token"]},
        ).status_code
        == 401
    )
    me = client.get(
        "/api/v1/auth/me", headers={"Authorization": "Bearer " + new["access_token"]}
    )
    assert me.status_code == 200
    assert set(me.json()) == {"id", "email", "name", "timezone"}
    assert (
        response.headers["cache-control"] == me.headers["cache-control"] == "no-store"
    )


def test_logout_revokes_only_selected_device(auth):
    client, _ = auth
    first = client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE).json()
    second = client.post("/api/v1/auth/sign-in", json=CREDS, headers=NATIVE).json()
    assert (
        client.post(
            "/api/v1/auth/logout",
            headers=NATIVE,
            json={"refresh_token": first["refresh_token"]},
        ).status_code
        == 204
    )
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + first["access_token"]},
        ).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/refresh",
            headers=NATIVE,
            json={"refresh_token": first["refresh_token"]},
        ).status_code
        == 401
    )
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + second["access_token"]},
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/v1/auth/refresh",
            headers=NATIVE,
            json={"refresh_token": second["refresh_token"]},
        ).status_code
        == 200
    )


@pytest.mark.parametrize("status_field", ["disabled_at", "deleted_at"])
def test_inactive_account_denied_across_auth_routes(auth, status_field):
    client, db = auth
    tokens = client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE).json()
    user = db.scalar(select(User))
    setattr(user, status_field, datetime.now(UTC))
    db.commit()
    assert (
        client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer " + tokens["access_token"]},
        ).status_code
        == 401
    )
    assert (
        client.post("/api/v1/auth/sign-in", json=CREDS, headers=NATIVE).status_code
        == 401
    )
    assert (
        client.post(
            "/api/v1/auth/refresh",
            headers=NATIVE,
            json={"refresh_token": tokens["refresh_token"]},
        ).status_code
        == 401
    )


def test_browser_cannot_select_native_token_delivery(auth):
    client, _ = auth
    headers = {**WEB, **NATIVE}
    response = client.post("/api/v1/auth/register", json=CREDS, headers=headers)
    assert response.status_code == 201
    assert "refresh_token" not in response.json()
    assert COOKIE in client.cookies
    assert (
        client.post("/api/v1/auth/refresh", json={}, headers=headers).status_code == 200
    )


def test_web_refresh_replay_and_cross_platform_use_rejected(auth):
    client, _ = auth
    client.post("/api/v1/auth/register", json=CREDS, headers=WEB)
    old = client.cookies.get(COOKIE)
    assert client.post("/api/v1/auth/refresh", json={}, headers=WEB).status_code == 200
    current = client.cookies.get(COOKIE)
    client.cookies.clear()
    assert (
        client.post(
            "/api/v1/auth/refresh", headers=NATIVE, json={"refresh_token": current}
        ).status_code
        == 401
    )
    client.cookies.set(COOKIE, old, path="/api/v1/auth")
    assert client.post("/api/v1/auth/refresh", json={}, headers=WEB).status_code == 401


def test_duplicate_registration_is_case_insensitive(auth):
    client, db = auth
    assert (
        client.post("/api/v1/auth/register", json=CREDS, headers=NATIVE).status_code
        == 201
    )
    assert (
        client.post(
            "/api/v1/auth/register",
            json={**CREDS, "email": CREDS["email"].upper()},
            headers=NATIVE,
        ).status_code
        == 409
    )
    assert len(list(db.scalars(select(User)))) == 1


@pytest.mark.parametrize("name", ["  Alex  ", "李明", "A" * 100])
def test_registration_persists_name_and_returns_it_in_profile(auth, name):
    client, db = auth
    response = client.post(
        "/api/v1/auth/register", json={**CREDS, "name": name}, headers=NATIVE
    )
    assert response.status_code == 201
    assert db.scalar(select(User)).name == name.strip()
    profile = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": "Bearer " + response.json()["access_token"]},
    )
    assert profile.status_code == 200
    assert profile.json()["name"] == name.strip()


@pytest.mark.parametrize("name", ["", "   ", "A" * 101, 123])
def test_registration_rejects_invalid_names(auth, name):
    client, db = auth
    response = client.post(
        "/api/v1/auth/register", json={**CREDS, "name": name}, headers=NATIVE
    )
    assert response.status_code == 422
    assert db.scalar(select(User)) is None


@pytest.mark.parametrize("native", [False, True])
def test_auth_service_rotates_and_revokes_tokens_without_http(auth, native):
    from app.schemas.auth import Credentials, RegistrationCredentials
    from app.services import auth as auth_service
    from app.services.errors import InvalidAccessToken, InvalidSession

    _, db = auth
    tokens = auth_service.register(RegistrationCredentials(**CREDS), db, native)
    user = auth_service.get_current_user(tokens.access_token, db)
    assert user.email == CREDS["email"].lower()
    record = db.scalar(select(AuthSession))
    expires_at = record.refresh_expires_at
    assert tokens.native is native
    assert record.access_hash == auth_service.digest(tokens.access_token)
    assert record.refresh_hash == auth_service.digest(tokens.refresh_token)
    assert tokens.access_token not in repr(tokens)
    assert tokens.refresh_token not in repr(tokens)

    with pytest.raises(InvalidSession):
        auth_service.refresh(tokens.refresh_token, not native, db)
    rotated = auth_service.refresh(tokens.refresh_token, native, db)
    assert record.refresh_expires_at == expires_at
    assert rotated.access_token != tokens.access_token
    assert rotated.refresh_token != tokens.refresh_token
    with pytest.raises(InvalidAccessToken):
        auth_service.get_current_user(tokens.access_token, db)
    with pytest.raises(InvalidSession):
        auth_service.refresh(tokens.refresh_token, native, db)
    assert auth_service.get_current_user(rotated.access_token, db).id == user.id

    auth_service.logout(rotated.refresh_token, native, db)
    with pytest.raises(InvalidAccessToken):
        auth_service.get_current_user(rotated.access_token, db)
    signed_in = auth_service.sign_in(Credentials(**CREDS), db, native)
    assert auth_service.get_current_user(signed_in.access_token, db).id == user.id
