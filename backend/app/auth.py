"""Email/password authentication with opaque, revocable token pairs."""

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_session
from app.models import AuthRateBucket, AuthSession, User

router = APIRouter(prefix="/auth", tags=["auth"])
DB = Annotated[Session, Depends(get_session)]
hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))
COOKIE = "wordrecall_refresh"


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def guard(request: Request, db: DB) -> None:
    settings = get_settings()
    origin = request.headers.get("origin")
    # Native requests have no browser Origin. Never trust a platform header to bypass CSRF.
    if origin is not None and origin not in settings.cors_origins:
        raise HTTPException(403, "Origin not allowed")
    if COOKIE in request.cookies and origin is None:
        raise HTTPException(403, "Origin required for cookie authentication")
    now = datetime.now(UTC)
    window = settings.auth_rate_window_seconds
    bucket = int(now.timestamp()) // window
    address = request.client.host if request.client else "unknown"
    key = hmac.new(
        settings.secret_key.get_secret_value().encode(),
        f"{address}:{bucket}".encode(),
        hashlib.sha256,
    ).hexdigest()
    db.execute(delete(AuthRateBucket).where(AuthRateBucket.expires_at <= now))
    try:
        with db.begin_nested():
            db.add(
                AuthRateBucket(
                    key=key, count=0, expires_at=now + timedelta(seconds=window * 2)
                )
            )
            db.flush()
    except IntegrityError:
        pass
    accepted = db.execute(
        update(AuthRateBucket)
        .where(
            AuthRateBucket.key == key, AuthRateBucket.count < settings.auth_rate_limit
        )
        .values(count=AuthRateBucket.count + 1)
        .returning(AuthRateBucket.key)
    ).scalar_one_or_none()
    db.commit()
    if accepted is None:
        raise HTTPException(
            429,
            "Too many authentication attempts",
            headers={"Retry-After": str(window)},
        )


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=320)
    password: SecretStr = Field(min_length=12, max_length=128)


class RegistrationCredentials(Credentials):
    # Optional for existing clients; new clients collect the name during sign-up.
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(default=None, min_length=32, max_length=256)


def native_request(request: Request) -> bool:
    return (
        request.headers.get("x-auth-platform") == "native"
        and "origin" not in request.headers
    )


def issue(
    db: Session,
    user: User,
    native: bool,
    response: Response,
    existing: AuthSession | None = None,
) -> dict[str, object]:
    settings = get_settings()
    now = datetime.now(UTC)
    access, refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    record = existing or AuthSession(
        user_id=user.id,
        native=native,
        refresh_expires_at=now + timedelta(seconds=settings.refresh_token_seconds),
    )
    record.access_hash = digest(access)
    record.refresh_hash = digest(refresh)
    record.access_expires_at = now + timedelta(seconds=settings.access_token_seconds)
    db.add(record)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    result: dict[str, object] = {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": settings.access_token_seconds,
    }
    if native:
        result["refresh_token"] = refresh
    else:
        response.set_cookie(
            COOKIE,
            refresh,
            httponly=True,
            secure=settings.auth_cookie_secure,
            samesite="strict",
            path="/api/v1/auth",
            max_age=max(0, int((record.refresh_expires_at - now).total_seconds())),
        )
    return result


@router.post("/register", status_code=201, dependencies=[Depends(guard)])
def register(
    body: RegistrationCredentials, request: Request, response: Response, db: DB
) -> dict[str, object]:
    user = User(
        name=body.name,
        email=str(body.email).lower(),
        password_hash=hasher.hash(body.password.get_secret_value()),
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Unable to register this email") from None
    return issue(db, user, native_request(request), response)


@router.post("/sign-in", dependencies=[Depends(guard)])
def sign_in(
    body: Credentials, request: Request, response: Response, db: DB
) -> dict[str, object]:
    user = db.scalar(select(User).where(User.email == str(body.email).lower()))
    stored = user.password_hash if user and user.password_hash else DUMMY_HASH
    try:
        valid: bool = hasher.verify(stored, body.password.get_secret_value())
    except (VerificationError, InvalidHashError):
        valid = False
    if (
        not valid
        or not user
        or not user.password_hash
        or user.disabled_at
        or user.deleted_at
    ):
        raise HTTPException(401, "Invalid email or password")
    if hasher.check_needs_rehash(stored):
        user.password_hash = hasher.hash(body.password.get_secret_value())
    return issue(db, user, native_request(request), response)


def refresh_record(body: RefreshInput, request: Request, db: Session) -> AuthSession:
    native = native_request(request)
    token = body.refresh_token if native else request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "Invalid or expired session")
    record = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_hash == digest(token), AuthSession.native == native)
        .with_for_update()
    )
    if not record or record.refresh_expires_at <= datetime.now(UTC):
        raise HTTPException(401, "Invalid or expired session")
    return record


@router.post("/refresh", dependencies=[Depends(guard)])
def refresh(
    body: RefreshInput, request: Request, response: Response, db: DB
) -> dict[str, object]:
    record = refresh_record(body, request, db)
    user = db.get(User, record.user_id)
    if not user or user.disabled_at or user.deleted_at:
        raise HTTPException(401, "Invalid or expired session")
    return issue(db, user, record.native, response, record)


@router.post("/logout", status_code=204, dependencies=[Depends(guard)])
def logout(body: RefreshInput, request: Request, response: Response, db: DB) -> None:
    record = refresh_record(body, request, db)
    db.delete(record)
    db.commit()
    response.delete_cookie(
        COOKIE,
        path="/api/v1/auth",
        secure=get_settings().auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"


def get_current_user(request: Request, db: DB) -> User:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    record = (
        db.scalar(select(AuthSession).where(AuthSession.access_hash == digest(token)))
        if scheme.lower() == "bearer" and token
        else None
    )
    user = db.get(User, record.user_id) if record else None
    if (
        not record
        or record.access_expires_at <= datetime.now(UTC)
        or not user
        or user.disabled_at
        or user.deleted_at
    ):
        raise HTTPException(
            401,
            "Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


@router.get("/me")
def me(
    response: Response, user: Annotated[User, Depends(get_current_user)]
) -> dict[str, str | None]:
    response.headers["Cache-Control"] = "no-store"
    return {
        "id": str(user.id),
        "email": user.email,
        "name": user.name,
        "timezone": user.timezone,
    }
