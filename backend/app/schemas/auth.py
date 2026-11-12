"""Validated authentication request bodies."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field, SecretStr, field_validator

from app.schemas.account import Timezone


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr = Field(max_length=320)
    password: SecretStr = Field(min_length=12, max_length=128)


class RegistrationCredentials(Credentials):
    timezone: Timezone = "UTC"
    # Optional for existing clients; new clients collect the name during sign-up.
    name: str | None = Field(default=None, min_length=1, max_length=100)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class RefreshInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    refresh_token: str | None = Field(default=None, min_length=32, max_length=256)
