from fastapi import APIRouter, Response

from app.api.auth import clear_refresh_cookie
from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.services import accounts

router = APIRouter()


@router.delete("/account", status_code=204)
def delete_account(response: Response, db: DB, user: CurrentUser) -> None:
    with service_errors():
        accounts.delete_account(db, user)
    clear_refresh_cookie(response)
