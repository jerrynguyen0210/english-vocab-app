"""Review sessions, answer validation, and atomic review scheduling.

Answer submission retains the account and review locks until its commit.
Duplicate attempts are checked before ticket expiry.
"""

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ReviewAttempt, ReviewState, User, Word
from app.schemas.reviews import (
    AnswerInput,
    AnswerResult,
    ChoiceRequest,
    ReviewItem,
    ReviewSelection,
    SessionItem,
    TypingSessionItem,
)
from app.services.accounts import lock_account
from app.services.dictionary import PartOfSpeech, review_parts
from app.services.errors import (
    ReviewConflict,
    ReviewNotFound,
)
from app.services.reviews.answers import answer_matches
from app.services.reviews.choices import review_options
from app.services.reviews.prompts import mask_target
from app.services.reviews.queries import review_totals
from app.services.reviews.scheduling import schedule_review
from app.services.reviews.selection import selected_words
from app.services.reviews.tickets import issue_ticket, valid_ticket

CHOICE_CANDIDATE_LIMIT = 200


def choice_profiles(
    db: Session, user: User, targets: list[str]
) -> dict[str, frozenset[PartOfSpeech]]:
    """Bound dictionary work to a candidate pool plus at most 50 session targets."""
    bank = db.scalars(
        select(Word.word)
        .where(Word.user_id == user.id)
        # Match the existing (user_id, normalised_word) unique index so this
        # bounded read does not need to sort an account's entire vocabulary.
        .order_by(Word.normalised_word)
        .limit(CHOICE_CANDIDATE_LIMIT)
    )
    return {word: review_parts(word) for word in dict.fromkeys([*bank, *targets])}


def next_reviews(db: Session, user: User, limit: int = 1) -> list[ReviewItem]:
    now = datetime.now(UTC)
    # Read the answer only to redact hints; never serialize it in the prompt.
    rows = db.execute(
        select(Word.id, Word.word, Word.english_explanation, Word.example_sentence)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.user_id == user.id, ReviewState.due_at <= now)
        .order_by(ReviewState.due_at, Word.id)
        .limit(min(limit, 50))
    )
    return [
        ReviewItem(
            word_id=row.id,
            english_explanation=mask_target(row.english_explanation, row.word),
            example_sentence=(
                mask_target(row.example_sentence, row.word)
                if row.example_sentence
                else None
            ),
        )
        for row in rows
    ]


def review_summary(db: Session, user: User) -> dict[str, int]:
    return review_totals(db, user, datetime.now(UTC))


def review_preparation(
    db: Session, user: User, selection: ReviewSelection
) -> dict[str, int]:
    now = datetime.now(UTC)
    matching = (
        db.scalar(
            select(func.count()).select_from(
                selected_words(user, now, selection).order_by(None).subquery()
            )
        )
        or 0
    )
    totals = review_totals(db, user, now)
    return {
        **totals,
        "count": min(matching, 50),
        "matching_count": matching,
    }


def review_session(
    db: Session, user: User, selection: ReviewSelection
) -> list[TypingSessionItem]:
    now = datetime.now(UTC)
    rows = db.execute(selected_words(user, now, selection).limit(50)).all()
    if not rows:
        return []
    saved_parts = (
        choice_profiles(db, user, [word.word for word, _ in rows])
        if selection.answer_mode == "choice"
        else {}
    )
    items: list[TypingSessionItem] = []
    for word, state in rows:
        attempt_id = uuid.uuid4()
        item = TypingSessionItem(
            word_id=word.id,
            attempt_id=attempt_id,
            review_token=issue_ticket(user.id, state, attempt_id, now),
            prompt_sentence=mask_target(word.review_prompt, word.word),
            english_explanation=mask_target(word.english_explanation, word.word),
            example_sentence=mask_target(word.example_sentence, word.word)
            if word.example_sentence
            else None,
        )
        if selection.answer_mode == "choice":
            items.append(
                SessionItem(
                    **item.model_dump(), choices=review_options(word.word, saved_parts)
                )
            )
        else:
            items.append(item)
    return items


def word_choices(
    word_id: uuid.UUID, body: ChoiceRequest, db: Session, user: User
) -> SessionItem:
    """Reveal D16 options only after an explicit switch to multiple choice."""
    pair = db.execute(
        select(Word, ReviewState)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.id == word_id, Word.user_id == user.id)
    ).first()
    if pair is None:
        raise ReviewNotFound("Review item not found")
    word, state = pair
    now = datetime.now(UTC)
    if not valid_ticket(body.review_token, user.id, state, body.attempt_id, now):
        raise ReviewConflict("Review session expired or changed. Start a new review.")
    return SessionItem(
        word_id=word.id,
        attempt_id=body.attempt_id,
        review_token=body.review_token,
        prompt_sentence=mask_target(word.review_prompt, word.word),
        english_explanation=mask_target(word.english_explanation, word.word),
        example_sentence=mask_target(word.example_sentence, word.word)
        if word.example_sentence
        else None,
        choices=review_options(word.word, choice_profiles(db, user, [word.word])),
    )


def submit_answer(
    word_id: uuid.UUID, body: AnswerInput, db: Session, user: User
) -> AnswerResult:
    lock_account(db, user)
    pair = db.execute(
        select(Word, ReviewState)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.id == word_id, Word.user_id == user.id)
        .with_for_update()
    ).first()
    if pair is None:
        raise ReviewNotFound("Review item not found")
    word, state = pair
    if body.attempt_id is not None:
        previous = db.get(ReviewAttempt, body.attempt_id)
        if previous is not None:
            if previous.user_id != user.id or previous.word_id != word.id:
                raise ReviewConflict("Submission identifier unavailable")
            if (
                previous.typed_answer != body.typed_answer
                or previous.time_taken_ms != body.time_taken_ms
            ):
                raise ReviewConflict("Submission payload changed")
            return AnswerResult(
                attempt_id=previous.id,
                result=previous.result,
                correct_word=word.word,
                next_due_at=previous.next_due_at or state.due_at,
            )
    now = datetime.now(UTC)
    if body.review_token is not None and not valid_ticket(
        body.review_token, user.id, state, body.attempt_id, now
    ):
        raise ReviewConflict("Review session expired or changed. Start a new review.")
    if body.review_token is None and state.due_at > now:
        raise ReviewConflict("Review item is not due")
    correct = answer_matches(body.typed_answer, word.word)
    result: Literal["correct", "incorrect"] = "correct" if correct else "incorrect"
    schedule_review(state, correct, now)
    attempt = ReviewAttempt(
        id=body.attempt_id or uuid.uuid4(),
        word_id=word.id,
        user_id=user.id,
        typed_answer=body.typed_answer,
        result=result,
        reviewed_at=now,
        time_taken_ms=body.time_taken_ms,
        next_due_at=state.due_at,
    )
    db.add(attempt)
    response = AnswerResult(
        attempt_id=attempt.id,
        result=result,
        correct_word=word.word,
        next_due_at=state.due_at,
    )
    db.commit()
    return response
