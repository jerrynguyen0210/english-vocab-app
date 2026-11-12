"""Immutable answer history, separate from mutable scheduling state."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.core.text import normalise_word
from app.core.time import UTCDateTime


class ReviewAttempt(Base):
    __tablename__ = "review_attempts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["word_id", "user_id"],
            ["words.id", "words.user_id"],
            name="fk_review_attempts_word_owner",
        ),
        CheckConstraint(
            "result IN ('correct', 'incorrect')", name="ck_review_attempts_result"
        ),
        CheckConstraint(
            "time_taken_ms >= 0", name="ck_review_attempts_time_nonnegative"
        ),
        Index("ix_review_attempts_word_reviewed", "word_id", "reviewed_at"),
        Index("ix_review_attempts_user_reviewed", "user_id", "reviewed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    word_id: Mapped[uuid.UUID] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column()
    typed_answer: Mapped[str] = mapped_column(Text)
    normalised_answer: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(String(9))
    reviewed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )
    time_taken_ms: Mapped[int] = mapped_column(Integer)

    @validates("typed_answer")
    def _set_normalised_answer(self, key: str, value: str) -> str:
        self.normalised_answer = normalise_word(value)
        return value


@event.listens_for(ReviewAttempt, "before_update")
@event.listens_for(ReviewAttempt, "before_delete")
def _reject_history_change(*args: object) -> None:
    raise ValueError("Review attempts are append-only")
