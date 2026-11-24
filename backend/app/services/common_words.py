"""Request-driven selection, generation, and atomic grading of Common practice."""

import time
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.openrouter_common import generate_common_questions
from app.llm.openrouter_review import ReviewError
from app.models import CommonPracticeQuestion, CommonWord, User, UserCommonWordProgress
from app.schemas.common_words import (
    BankWord,
    CommonAnswerResult,
    CommonBatch,
    CommonQuestion,
    GeneratedCommonBatch,
)
from app.services.accounts import lock_account, lock_account_by_id
from app.services.errors import (
    CommonGenerationUnavailable,
    CommonQuestionNotFound,
    ReviewConflict,
)


def select_unlearned(db: Session, user_id: UUID) -> list[BankWord]:
    learned = set(
        db.scalars(
            select(UserCommonWordProgress.common_word_id).where(
                UserCommonWordProgress.user_id == user_id,
                UserCommonWordProgress.learned_at.is_not(None),
            )
        )
    )
    selected: list[BankWord] = []
    cursor: UUID | None = None
    while len(selected) < 10:
        statement = select(CommonWord).order_by(CommonWord.id).limit(10)
        if cursor is not None:
            statement = statement.where(CommonWord.id > cursor)
        page = list(db.scalars(statement))
        if not page:
            break
        cursor = page[-1].id
        selected.extend(
            BankWord.model_validate(word) for word in page if word.id not in learned
        )
        selected = selected[:10]
        if len(page) < 10:
            break
    return selected


def get_batch(db: Session, user: User) -> CommonBatch:
    user_id = user.id
    settings = get_settings()
    deadline = time.monotonic() + settings.common_words_timeout_seconds
    # Another session can learn during generation. Rebuild within a bounded total deadline.
    for _ in range(3):
        words = select_unlearned(db, user_id)
        bank_available = (
            bool(words) or db.scalar(select(CommonWord.id).limit(1)) is not None
        )
        db.commit()  # End auth/selection transaction before provider I/O.
        if not words:
            if not bank_available:
                raise CommonGenerationUnavailable(
                    "Common words are not available yet. Please try again later."
                )
            return CommonBatch(status="complete")
        try:
            generated = generate_common_questions(
                words,
                model=settings.openrouter_model,
                api_key=settings.openrouter_api_key.get_secret_value(),
                base_url=settings.openrouter_url,
                timeout=deadline - time.monotonic(),
            )
            # Check here as well so service callers cannot insert a partial/mismatched batch.
            questions = GeneratedCommonBatch(questions=generated).questions
            if len(questions) != len(words) or {
                q.common_word_id for q in questions
            } != {w.id for w in words}:
                raise ValueError("Incomplete question batch")
        except (ReviewError, ValueError):
            raise CommonGenerationUnavailable(
                "Could not prepare Common questions. Please retry."
            ) from None
        lock_account_by_id(db, user_id)
        learned = db.scalar(
            select(UserCommonWordProgress.common_word_id)
            .where(
                UserCommonWordProgress.user_id == user_id,
                UserCommonWordProgress.common_word_id.in_([word.id for word in words]),
                UserCommonWordProgress.learned_at.is_not(None),
            )
            .limit(1)
        )
        if learned is not None:
            db.rollback()
            continue
        by_id = {question.common_word_id: question for question in questions}
        response: list[CommonQuestion] = []
        now = datetime.now(UTC)
        for word in words:
            generated_question = by_id[word.id]
            record = CommonPracticeQuestion(
                user_id=user_id,
                common_word_id=word.id,
                question=generated_question.question,
                choices=generated_question.choices,
                correct_index=generated_question.correct_index,
            )
            db.add(record)
            progress = db.get(UserCommonWordProgress, (user_id, word.id))
            if progress is None:
                progress = UserCommonWordProgress(
                    user_id=user_id, common_word_id=word.id
                )
                db.add(progress)
            progress.last_presented_at = now
            db.flush()
            response.append(
                CommonQuestion(
                    id=record.id,
                    word=word.word,
                    ipa=word.ipa,
                    partOfSpeech=word.part_of_speech,
                    explanation=word.english_explanation,
                    example=word.example_sentence,
                    question=record.question,
                    choices=record.choices,
                )
            )
        db.commit()
        return CommonBatch(status="ready", questions=response)
    raise CommonGenerationUnavailable(
        "Learning progress changed. Please retry this batch."
    )


def answer_question(
    db: Session, user: User, question_id: UUID, selected_index: int
) -> CommonAnswerResult:
    lock_account(db, user)
    question = db.scalar(
        select(CommonPracticeQuestion)
        .where(
            CommonPracticeQuestion.id == question_id,
            CommonPracticeQuestion.user_id == user.id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if question is None:
        raise CommonQuestionNotFound("Common question not found")
    if (
        question.selected_index is not None
        and question.selected_index != selected_index
    ):
        raise ReviewConflict("This question has already been answered")
    correct = selected_index == question.correct_index
    if question.answered_at is None:
        now = datetime.now(UTC)
        question.selected_index = selected_index
        question.answered_at = now
        if correct:
            progress = db.get(
                UserCommonWordProgress,
                (user.id, question.common_word_id),
                populate_existing=True,
            )
            if progress is None:
                progress = UserCommonWordProgress(
                    user_id=user.id, common_word_id=question.common_word_id
                )
                db.add(progress)
            if progress.learned_at is None:
                progress.learned_at = now
    word = db.get(CommonWord, question.common_word_id)
    assert word is not None
    result = CommonAnswerResult(
        result="correct" if correct else "incorrect",
        correctIndex=question.correct_index,
        explanation=word.english_explanation,
    )
    db.commit()
    return result
