"""Resume batches and generate them durably outside HTTP requests."""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal, cast

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.openrouter_review import ReviewError
from app.models import (
    CommonPracticeBatch,
    CommonPracticeQuestion,
    CommonWord,
    User,
    UserCommonWordProgress,
)
from app.schemas.common_words import CommonBatchStatus, CommonQuestion
from app.services.accounts import lock_account
from app.services.common_words import get_batch
from app.services.errors import CommonQuestionNotFound, ServiceError

logger = logging.getLogger(__name__)


def expire_jobs(db: Session, user_id: uuid.UUID | None = None) -> None:
    statement = update(CommonPracticeBatch)
    if user_id is not None:
        statement = statement.where(CommonPracticeBatch.user_id == user_id)
    db.execute(
        statement.where(
            CommonPracticeBatch.status == "generating",
            CommonPracticeBatch.available_at <= datetime.now(UTC),
        ).values(status="failed")
    )


def batch_status(db: Session, batch: CommonPracticeBatch) -> CommonBatchStatus:
    questions = []
    if batch.status == "ready":
        ids = [uuid.UUID(value) for value in batch.question_ids]
        rows = db.execute(
            select(CommonPracticeQuestion, CommonWord)
            .join(CommonWord, CommonWord.id == CommonPracticeQuestion.common_word_id)
            .outerjoin(
                UserCommonWordProgress,
                (UserCommonWordProgress.common_word_id == CommonWord.id)
                & (UserCommonWordProgress.user_id == batch.user_id),
            )
            .where(
                CommonPracticeQuestion.id.in_(ids),
                CommonPracticeQuestion.user_id == batch.user_id,
                CommonPracticeQuestion.answered_at.is_(None),
                UserCommonWordProgress.learned_at.is_(None),
            )
        )
        by_id = {
            str(question.id): CommonQuestion(
                id=question.id,
                word=word.word,
                ipa=word.ipa,
                partOfSpeech=word.part_of_speech,
                explanation=word.english_explanation,
                example=word.example_sentence,
                question=question.question,
                choices=question.choices,
            )
            for question, word in rows
        }
        questions = [by_id[value] for value in batch.question_ids if value in by_id]
    return CommonBatchStatus(
        id=batch.id,
        status=cast(
            Literal["pending", "generating", "ready", "complete", "failed"],
            batch.status,
        ),
        questions=questions,
    )


def start_batch(db: Session, user: User) -> CommonBatchStatus:
    # One slot per user, serialized with answer submission and account erasure.
    lock_account(db, user)
    expire_jobs(db, user.id)
    batch = db.get(CommonPracticeBatch, user.id, populate_existing=True)
    if batch is not None:
        result = batch_status(db, batch)
        if batch.status in ("pending", "generating") or result.questions:
            db.commit()
            return result
    else:
        batch = CommonPracticeBatch(user_id=user.id)
        db.add(batch)
    batch.id = uuid.uuid4()  # Fences any old worker, including after a crash.
    batch.status = "pending"
    batch.question_ids = []
    batch.available_at = datetime.now(UTC)
    db.commit()
    return batch_status(db, batch)


def read_batch(db: Session, user: User, batch_id: uuid.UUID) -> CommonBatchStatus:
    batch = db.scalar(
        select(CommonPracticeBatch).where(
            CommonPracticeBatch.user_id == user.id, CommonPracticeBatch.id == batch_id
        )
    )
    if batch is None:
        raise CommonQuestionNotFound("Common batch not found")
    expire_jobs(db, user.id)
    db.refresh(batch)
    if batch.id != batch_id:
        raise CommonQuestionNotFound("Common batch not found")
    result = batch_status(db, batch)
    if result.status == "ready" and not result.questions:
        # Another device may have answered the batch, or an operator removed
        # its vocabulary. Never describe an exhausted batch as all words learned.
        result.status = "failed"
    db.commit()
    return result


def process_one(engine: Engine) -> bool:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        expire_jobs(db)
        batch = db.scalar(
            select(CommonPracticeBatch)
            .where(CommonPracticeBatch.status == "pending")
            .order_by(CommonPracticeBatch.available_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if batch is None:
            return False
        batch_id, user_id = batch.id, batch.user_id
        claimed = db.execute(
            update(CommonPracticeBatch)
            .where(
                CommonPracticeBatch.id == batch_id,
                CommonPracticeBatch.status == "pending",
            )
            .values(
                status="generating",
                available_at=now
                + timedelta(seconds=get_settings().common_words_timeout_seconds + 60),
            )
            .returning(CommonPracticeBatch.id)
        ).scalar_one_or_none()
        if claimed is None:
            return False
    try:
        with Session(engine) as db:
            user = db.get(User, user_id)
            if user is not None:
                get_batch(db, user, batch_id=batch_id)
    except (ServiceError, ReviewError, ValueError):
        # Never log provider bodies or user vocabulary. A failed batch requires
        # an explicit retry; crashes expire their lease rather than retry forever.
        logger.warning("Common batch generation failed")
        with Session(engine) as db, db.begin():
            db.execute(
                update(CommonPracticeBatch)
                .where(
                    CommonPracticeBatch.id == batch_id,
                    CommonPracticeBatch.status == "generating",
                )
                .values(status="failed")
            )
    return True
