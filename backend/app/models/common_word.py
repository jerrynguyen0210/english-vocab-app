"""Shared Common vocabulary, per-user learning, and owned practice questions."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import UTCDateTime


class CommonWord(Base):
    __tablename__ = "common_words"
    __table_args__ = (
        CheckConstraint("length(trim(word)) > 0", name="ck_common_bank_word"),
        CheckConstraint(
            "length(trim(normalised_word)) > 0", name="ck_common_bank_normalised"
        ),
        CheckConstraint(
            "length(trim(english_explanation)) > 0", name="ck_common_bank_meaning"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    word: Mapped[str] = mapped_column(Text)
    normalised_word: Mapped[str] = mapped_column(Text, unique=True)
    ipa: Mapped[str | None] = mapped_column(String(120))
    part_of_speech: Mapped[str] = mapped_column(String(32))
    english_explanation: Mapped[str] = mapped_column(Text)
    example_sentence: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )


class UserCommonWordProgress(Base):
    __tablename__ = "user_common_word_progress"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    common_word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("common_words.id"), primary_key=True
    )
    last_presented_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    learned_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class CommonPracticeQuestion(Base):
    __tablename__ = "common_practice_questions"
    __table_args__ = (
        CheckConstraint(
            "correct_index BETWEEN 0 AND 3", name="ck_common_practice_correct"
        ),
        CheckConstraint(
            "selected_index IS NULL OR selected_index BETWEEN 0 AND 3",
            name="ck_common_practice_selected",
        ),
        CheckConstraint(
            "(selected_index IS NULL AND answered_at IS NULL) OR (selected_index IS NOT NULL AND answered_at IS NOT NULL)",
            name="ck_common_practice_answer_pair",
        ),
        Index("ix_common_practice_user", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE")
    )
    common_word_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("common_words.id"))
    question: Mapped[str] = mapped_column(Text)
    choices: Mapped[list[str]] = mapped_column(JSON)
    correct_index: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    selected_index: Mapped[int | None]
    answered_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
