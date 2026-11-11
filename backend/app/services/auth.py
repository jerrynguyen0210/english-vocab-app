"""Password authentication and revocable sessions, independent of HTTP.

Refresh rotation and logout retain the session lock through their commit.
Registration commits the user and initial session together.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuthRateBucket, AuthSession, User
from app.schemas.auth import Credentials, RegistrationCredentials
from app.services.errors import (
    AuthRateLimited,
    InvalidAccessToken,
    InvalidCredentials,
    InvalidSession,
    RegistrationConflict,
)

hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = hasher.hash(secrets.token_urlsafe(32))


@dataclass(frozen=True, repr=False)
class IssuedTokens:
    """Transient plaintext tokens; only their hashes are persisted."""

    access_token: str
    refresh_token: str
    expires_in: int
    refresh_max_age: int
    native: bool


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def enforce_rate_limit(db: Session, address: str) -> None:
    settings = get_settings()
    now = datetime.now(UTC)
    window = settings.auth_rate_window_seconds
    bucket = int(now.timestamp()) // window
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
        raise AuthRateLimited(window)


def issue(
    db: Session, user: User, native: bool, existing: AuthSession | None = None
) -> IssuedTokens:
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
    return IssuedTokens(
        access_token=access,
        refresh_token=refresh,
        expires_in=settings.access_token_seconds,
        refresh_max_age=max(0, int((record.refresh_expires_at - now).total_seconds())),
        native=native,
    )


def register(body: RegistrationCredentials, db: Session, native: bool) -> IssuedTokens:
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
        raise RegistrationConflict("Unable to register this email") from None
    return issue(db, user, native)


def sign_in(body: Credentials, db: Session, native: bool) -> IssuedTokens:
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
        raise InvalidCredentials("Invalid email or password")
    if hasher.check_needs_rehash(stored):
        user.password_hash = hasher.hash(body.password.get_secret_value())
    return issue(db, user, native)


def refresh_record(token: str | None, native: bool, db: Session) -> AuthSession:
    if not token:
        raise InvalidSession("Invalid or expired session")
    record = db.scalar(
        select(AuthSession)
        .where(AuthSession.refresh_hash == digest(token), AuthSession.native == native)
        .with_for_update()
    )
    if not record or record.refresh_expires_at <= datetime.now(UTC):
        raise InvalidSession("Invalid or expired session")
    return record


def refresh(token: str | None, native: bool, db: Session) -> IssuedTokens:
    record = refresh_record(token, native, db)
    user = db.get(User, record.user_id)
    if not user or user.disabled_at or user.deleted_at:
        raise InvalidSession("Invalid or expired session")
    return issue(db, user, record.native, record)


def logout(token: str | None, native: bool, db: Session) -> None:
    record = refresh_record(token, native, db)
    db.delete(record)
    db.commit()


def get_current_user(token: str | None, db: Session) -> User:
    record = (
        db.scalar(select(AuthSession).where(AuthSession.access_hash == digest(token)))
        if token
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
        raise InvalidAccessToken("Invalid or expired access token")
    return user
