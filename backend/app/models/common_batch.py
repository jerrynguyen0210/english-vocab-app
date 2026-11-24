"""One resumable Common practice batch per account."""

import uuid
from datetime import datetime

from sqlalchemy import JSON, CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.time import UTCDateTime


class CommonPracticeBatch(Base):
    __tablename__ = "common_practice_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'generating', 'ready', 'complete', 'failed')",
            name="ck_common_batch_status",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[uuid.UUID] = mapped_column(unique=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    question_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    available_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
