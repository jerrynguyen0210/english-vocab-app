"""Validated account profile and timezone preferences."""

import uuid
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AfterValidator, BaseModel, ConfigDict, Field


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError(
            "Use a valid IANA timezone, such as Australia/Adelaide"
        ) from None
    return value


Timezone = Annotated[
    str, Field(min_length=1, max_length=255), AfterValidator(validate_timezone)
]


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: Timezone


class AccountProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    name: str | None
    timezone: str
