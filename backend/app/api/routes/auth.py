"""Authentication endpoints; session rules live in the auth service."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response

from app.api.auth import (
    clear_refresh_cookie,
    native_request,
    refresh_token,
    token_response,
)
from app.api.dependencies import DB, get_current_user, guard
from app.api.errors import service_errors
from app.models import User
from app.schemas.auth import Credentials, RefreshInput, RegistrationCredentials
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=201, dependencies=[Depends(guard)])
def register(
    body: RegistrationCredentials, request: Request, response: Response, db: DB
) -> dict[str, object]:
    with service_errors():
        tokens = auth.register(body, db, native_request(request))
    return token_response(tokens, response)


@router.post("/sign-in", dependencies=[Depends(guard)])
def sign_in(
    body: Credentials, request: Request, response: Response, db: DB
) -> dict[str, object]:
    with service_errors():
        tokens = auth.sign_in(body, db, native_request(request))
    return token_response(tokens, response)


@router.post("/refresh", dependencies=[Depends(guard)])
def refresh(
    body: RefreshInput, request: Request, response: Response, db: DB
) -> dict[str, object]:
    with service_errors():
        tokens = auth.refresh(refresh_token(body, request), native_request(request), db)
    return token_response(tokens, response)


@router.post("/logout", status_code=204, dependencies=[Depends(guard)])
def logout(body: RefreshInput, request: Request, response: Response, db: DB) -> None:
    with service_errors():
        auth.logout(refresh_token(body, request), native_request(request), db)
    clear_refresh_cookie(response)


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
