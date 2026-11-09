"""Only token digests are persisted; rate limits are shared across workers."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import UTCDateTime


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    access_hash: Mapped[str] = mapped_column(String(64), unique=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    access_expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    refresh_expires_at: Mapped[datetime] = mapped_column(UTCDateTime())
    native: Mapped[bool]


class AuthRateBucket(Base):
    __tablename__ = "auth_rate_buckets"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int]
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
