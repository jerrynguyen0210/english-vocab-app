"""Durable prompt generation jobs; completed jobs are removed."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import UTCDateTime


class PromptJob(Base):
    __tablename__ = "prompt_jobs"
    __table_args__ = (
        Index(
            "ix_prompt_jobs_pending_available_at",
            "available_at",
            "word_id",
            postgresql_where=text("failed_at IS NULL"),
            sqlite_where=text("failed_at IS NULL"),
        ),
    )

    word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    lease_token: Mapped[uuid.UUID | None] = mapped_column()
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_category: Mapped[str | None] = mapped_column(String(32))
