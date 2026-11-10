"""Current scheduling state for a vocabulary word."""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Float, ForeignKey, Integer, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import UTCDateTime


class ReviewState(Base):
    __tablename__ = "review_states"
    __table_args__ = (
        CheckConstraint("repetitions >= 0", name="ck_review_repetitions"),
        CheckConstraint("interval_days >= 0", name="ck_review_interval"),
        CheckConstraint("ease_factor >= 1.3", name="ck_review_ease"),
        CheckConstraint("level >= 0", name="ck_review_states_level_nonnegative"),
        CheckConstraint(
            "correct_count >= 0", name="ck_review_states_correct_nonnegative"
        ),
        CheckConstraint(
            "incorrect_count >= 0", name="ck_review_states_incorrect_nonnegative"
        ),
    )

    word_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("words.id", ondelete="CASCADE"), primary_key=True
    )
    level: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    due_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now(), index=True
    )
    correct_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    incorrect_count: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    last_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    repetitions: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    interval_days: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    ease_factor: Mapped[float] = mapped_column(Float, server_default=text("2.5"))
