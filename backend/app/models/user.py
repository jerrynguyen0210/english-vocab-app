"""Account identity and lifecycle; authentication flows are defined separately."""

import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import CheckConstraint, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.core.time import UTCDateTime


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "password_hash IS NOT NULL OR auth_provider_id IS NOT NULL",
            name="ck_users_auth_identity",
        ),
        CheckConstraint("length(trim(email)) > 0", name="ck_users_email_nonempty"),
        CheckConstraint(
            "password_hash IS NULL OR length(trim(password_hash)) > 0",
            name="ck_users_password_hash_nonempty",
        ),
        CheckConstraint(
            "auth_provider_id IS NULL OR length(trim(auth_provider_id)) > 0",
            name="ck_users_auth_provider_id_nonempty",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(1024))
    auth_provider_id: Mapped[str | None] = mapped_column(String(512), unique=True)
    timezone: Mapped[str] = mapped_column(String(255), server_default=text("'UTC'"))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    disabled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    @validates("timezone")
    def _validate_timezone(self, key: str, value: str) -> str:
        ZoneInfo(value)
        return value
