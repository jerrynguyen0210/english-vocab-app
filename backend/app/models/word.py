"""User-owned vocabulary with normalized duplicate detection."""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, validates

from app.core.database import Base
from app.core.text import normalise_word
from app.core.time import UTCDateTime


class Word(Base):
    __tablename__ = "words"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_words_id_user"),
        UniqueConstraint("user_id", "normalised_word", name="uq_words_user_normalised"),
        CheckConstraint("length(trim(word)) > 0", name="ck_words_word_nonempty"),
        CheckConstraint(
            "length(trim(normalised_word)) > 0", name="ck_words_normalised_nonempty"
        ),
        CheckConstraint(
            "length(trim(english_explanation)) > 0",
            name="ck_words_explanation_nonempty",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    word: Mapped[str] = mapped_column(Text)
    normalised_word: Mapped[str] = mapped_column(Text)
    english_explanation: Mapped[str] = mapped_column(Text)
    example_sentence: Mapped[str | None] = mapped_column(Text)
    review_prompt: Mapped[str] = mapped_column(Text, server_default="_____")
    embedding_vector: Mapped[list[float] | None] = mapped_column(JSON)
    embedding_model: Mapped[str | None] = mapped_column(Text)
    embedding_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), server_default=func.now()
    )

    @validates("word")
    def _set_normalised_word(self, key: str, value: str) -> str:
        self.normalised_word = normalise_word(value)
        self.embedding_vector = None
        self.embedding_hash = None
        return value

    @validates("english_explanation", "example_sentence")
    def _invalidate_embedding(self, key: str, value: str | None) -> str | None:
        self.embedding_vector = None
        self.embedding_hash = None
        return value
