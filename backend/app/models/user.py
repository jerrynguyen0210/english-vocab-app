"""Account identity and lifecycle; authentication flows are defined separately."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


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
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(1024))
    auth_provider_id: Mapped[str | None] = mapped_column(String(512), unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
