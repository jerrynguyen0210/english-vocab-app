"""User-owned generated questions and one durable refill job per account."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import UTCDateTime


class CommonWordQuestion(Base):
    __tablename__ = "common_word_questions"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "normalised_word", name="uq_common_words_user_word"
        ),
        CheckConstraint("correct_index BETWEEN 0 AND 3", name="ck_common_words_answer"),
        Index("ix_common_words_user_presented", "user_id", "last_presented_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    word: Mapped[str] = mapped_column(Text)
    normalised_word: Mapped[str] = mapped_column(Text)
    part_of_speech: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text)
    example: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[str]] = mapped_column(JSON)
    correct_index: Mapped[int] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    last_presented_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    learned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class CommonWordJob(Base):
    __tablename__ = "common_word_jobs"
    __table_args__ = (Index("ix_common_word_jobs_available", "available_at"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    available_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    lease_token: Mapped[uuid.UUID | None] = mapped_column()
    failed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    failure_category: Mapped[str | None] = mapped_column(String(32))
