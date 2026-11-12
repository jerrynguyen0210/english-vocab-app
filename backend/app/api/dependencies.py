"""Database and authentication dependencies at the HTTP boundary."""

from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.api.auth_transport import COOKIE
from app.api.errors import service_errors
from app.core.config import get_settings
from app.core.database import get_session
from app.models import User
from app.services import auth

DB = Annotated[Session, Depends(get_session)]


def guard(request: Request, db: DB) -> None:
    settings = get_settings()
    origin = request.headers.get("origin")
    # Native requests have no browser Origin. Never trust a platform header to bypass CSRF.
    if origin is not None and origin not in settings.cors_origins:
        raise HTTPException(403, "Origin not allowed")
    if COOKIE in request.cookies and origin is None:
        raise HTTPException(403, "Origin required for cookie authentication")
    address = request.client.host if request.client else "unknown"
    with service_errors():
        auth.enforce_rate_limit(db, address)


def get_current_user(request: Request, db: DB) -> User:
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    with service_errors():
        return auth.get_current_user(token if scheme.lower() == "bearer" else None, db)


CurrentUser = Annotated[User, Depends(get_current_user)]
