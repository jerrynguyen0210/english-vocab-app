from fastapi import APIRouter, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.auth import COOKIE
from app.core.config import get_settings
from app.services import accounts

router = APIRouter()


@router.delete("/account", status_code=204)
def delete_account(response: Response, db: DB, user: CurrentUser) -> None:
    with service_errors():
        accounts.delete_account(db, user)
    response.delete_cookie(
        COOKIE,
        path="/api/v1/auth",
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
