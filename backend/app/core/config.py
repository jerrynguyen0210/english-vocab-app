from functools import lru_cache
from pathlib import Path
from typing import Literal

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
    app_environment: Literal["development", "test", "preview", "production"] = (
        "development"
    )
    migration_backup_dir: Path | None = None
    cors_origins: list[str] = []

    access_token_seconds: int = Field(default=900, ge=1)
    refresh_token_seconds: int = Field(default=2592000, ge=1)
    auth_rate_limit: int = Field(default=20, ge=1)
    auth_rate_window_seconds: int = Field(default=60, ge=1)
    auth_cookie_secure: bool = True
    ollama_url: str = "http://192.168.0.108:11434"
    ollama_model: str = Field(default="translategemma:4b", min_length=1)
    ollama_timeout_seconds: float = Field(default=120, gt=0, allow_inf_nan=False)
    prompt_job_max_attempts: int = Field(default=5, ge=1, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
