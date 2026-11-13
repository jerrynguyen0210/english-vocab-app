"""Serve stored, unsaved Common questions; queue a durable refill when empty."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CommonWordJob, CommonWordQuestion, User, Word
from app.schemas.common_words import CommonBatch, CommonBatchRequest, CommonQuestion
from app.services.accounts import lock_account
from app.services.errors import CommonQuestionNotFound, InvalidCommonAnswer


def mark_learned(
    db: Session, user: User, question_id: UUID, selected_index: int
) -> None:
    lock_account(db, user)
    question = db.scalar(
        select(CommonWordQuestion).where(
            CommonWordQuestion.id == question_id,
            CommonWordQuestion.user_id == user.id,
        )
    )
    if question is None:
        raise CommonQuestionNotFound("Common word question not found")
    if selected_index != question.correct_index:
        raise InvalidCommonAnswer("Choose the correct meaning to mark a word learned")
    # Retrying after a lost response must preserve the original learning time.
    if question.learned_at is None:
        question.learned_at = datetime.now(UTC)
    db.commit()


def get_batch(db: Session, user: User, body: CommonBatchRequest) -> CommonBatch:
    lock_account(db, user)
    # Recheck saved words on every fetch, including words saved after generation
    # or on another device. Never change the saved bank or review schedule here.
    saved = (
        select(Word.id)
        .where(
            Word.user_id == user.id,
            Word.normalised_word == CommonWordQuestion.normalised_word,
        )
        .exists()
    )
    questions = db.scalars(
        select(CommonWordQuestion)
        .where(
            CommonWordQuestion.user_id == user.id,
            CommonWordQuestion.learned_at.is_(None),
            ~saved,
            CommonWordQuestion.id.not_in(body.exclude_ids),
        )
        .order_by(
            CommonWordQuestion.last_presented_at.asc().nulls_first(),
            CommonWordQuestion.created_at,
            CommonWordQuestion.id,
        )
        .limit(10)
    ).all()
    now = datetime.now(UTC)
    if questions:
        result = [
            CommonQuestion(
                id=item.id,
                word=item.word,
                ipa=item.ipa,
                part_of_speech=item.part_of_speech,
                explanation=item.explanation,
                example=item.example,
                choices=item.choices,
                correct_index=item.correct_index,
            )
            for item in questions
        ]
        for item in questions:
            item.last_presented_at = now
        db.commit()
        return CommonBatch(status="ready", questions=result)
    job = db.get(CommonWordJob, user.id)
    if job is None:
        db.add(CommonWordJob(user_id=user.id))
    elif job.failed_at is not None:
        # Polling or rapid retries cannot trigger unbounded model calls.
        if job.failed_at + timedelta(seconds=60) > now:
            db.commit()
            return CommonBatch(status="failed")
        job.failed_at = None
        job.failure_category = None
        job.attempts = 0
        job.lease_token = None
        job.available_at = now
    db.commit()
    return CommonBatch(status="pending")
