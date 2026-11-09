from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    secret_key: SecretStr
    cors_origins: list[str] = []

    access_token_seconds: int = Field(default=900, ge=1)
    refresh_token_seconds: int = Field(default=2592000, ge=1)
    auth_rate_limit: int = Field(default=20, ge=1)
    auth_rate_window_seconds: int = Field(default=60, ge=1)
    auth_cookie_secure: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
