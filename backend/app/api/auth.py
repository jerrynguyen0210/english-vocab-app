"""Browser/native token transport and refresh-cookie policy."""

from fastapi import Request, Response

from app.core.config import get_settings
from app.schemas.auth import RefreshInput
from app.services.auth import IssuedTokens

COOKIE = "wordrecall_refresh"


def native_request(request: Request) -> bool:
    return (
        request.headers.get("x-auth-platform") == "native"
        and "origin" not in request.headers
    )


def refresh_token(body: RefreshInput, request: Request) -> str | None:
    return (
        body.refresh_token if native_request(request) else request.cookies.get(COOKIE)
    )


def token_response(tokens: IssuedTokens, response: Response) -> dict[str, object]:
    response.headers["Cache-Control"] = "no-store"
    result: dict[str, object] = {
        "access_token": tokens.access_token,
        "token_type": "bearer",
        "expires_in": tokens.expires_in,
    }
    if tokens.native:
        result["refresh_token"] = tokens.refresh_token
    else:
        response.set_cookie(
            COOKIE,
            tokens.refresh_token,
            httponly=True,
            secure=get_settings().auth_cookie_secure,
            samesite="strict",
            path="/api/v1/auth",
            max_age=tokens.refresh_max_age,
        )
    return result


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE,
        path="/api/v1/auth",
        secure=get_settings().auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
