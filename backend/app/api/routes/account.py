from fastapi import APIRouter, Response

from app.api.auth_transport import clear_refresh_cookie
from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.account import AccountProfile, AccountUpdate
from app.services import accounts

router = APIRouter()


@router.patch("/account", response_model=AccountProfile)
def update_account(
    body: AccountUpdate, response: Response, db: DB, user: CurrentUser
) -> AccountProfile:
    with service_errors():
        profile = AccountProfile.model_validate(accounts.update_account(db, user, body))
    response.headers["Cache-Control"] = "no-store"
    return profile


@router.delete("/account", status_code=204)
def delete_account(response: Response, db: DB, user: CurrentUser) -> None:
    with service_errors():
        accounts.delete_account(db, user)
    clear_refresh_cookie(response)
