"""HTTP dependency aliases shared by vocabulary routes."""

from typing import Annotated

from fastapi import Depends

from app.auth import DB, get_current_user
from app.models import User

CurrentUser = Annotated[User, Depends(get_current_user)]

__all__ = ["DB", "CurrentUser"]
