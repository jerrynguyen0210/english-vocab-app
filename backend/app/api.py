"""Version-one vocabulary and typed-recall API."""

import uuid
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from app.auth import COOKIE, DB, get_current_user
from app.core.config import get_settings
from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word
from app.models.word import normalise_word
from app.services.dictionary import (
    DictionaryEntry,
    PartOfSpeech,
    VerbForm,
    review_parts,
    search_dictionary,
)
from app.services.review_choices import review_options
from app.services.review_preparation import ReviewSelection, selected_words
from app.services.review_prompt import mask_target, prompt_sentence
from app.services.review_queue import (
    answer_matches,
    remaining_daily_reviews,
    review_totals,
    schedule_review,
)
from app.services.review_ticket import issue_ticket, valid_ticket

router = APIRouter()
CurrentUser = Annotated[User, Depends(get_current_user)]


def lock_account(db: DB, user: User) -> None:
    # Serialize mutations with account erasure and recheck after acquiring the lock.
    active = db.scalar(
        select(User.id)
        .where(
            User.id == user.id, User.deleted_at.is_(None), User.disabled_at.is_(None)
        )
        .with_for_update()
    )
    if active is None:
        raise HTTPException(401, "Account unavailable")


class CreateWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=200)
    english_explanation: str = Field(min_length=1, max_length=5000)

    example_sentence: str | None = Field(default=None, max_length=5000)

    @field_validator("example_sentence")
    @classmethod
    def optional_sentence(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("word", "english_explanation")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not normalise_word(value):
            raise ValueError("Must not be blank")
        return value.strip()


class WordCreated(BaseModel):
    example_sentence: str | None = None
    id: uuid.UUID
    word: str
    english_explanation: str


class ReviewItem(BaseModel):
    word_id: uuid.UUID
    english_explanation: str
    example_sentence: str | None = None


class TypingSessionItem(ReviewItem):
    prompt_sentence: str
    attempt_id: uuid.UUID
    review_token: str


class SessionItem(TypingSessionItem):
    choices: list[str] = Field(min_length=4, max_length=4)

    @field_validator("choices")
    @classmethod
    def four_unique_choices(cls, values: list[str]) -> list[str]:
        if (
            len(values) != 4
            or any(not normalise_word(value) for value in values)
            or len({normalise_word(value) for value in values}) != 4
        ):
            raise ValueError("Multiple choice requires four distinct nonblank options")
        return values


class ChoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: uuid.UUID
    review_token: str = Field(max_length=4096)


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: uuid.UUID | None = None
    review_token: str | None = Field(default=None, max_length=4096)
    typed_answer: str = Field(max_length=200)
    time_taken_ms: int = Field(ge=0, le=2147483647, strict=True)


class AnswerResult(BaseModel):
    attempt_id: uuid.UUID
    result: Literal["correct", "incorrect"]
    correct_word: str
    next_due_at: datetime


class WordSearchResult(DictionaryEntry):
    saved: bool = False


@router.get("/words/search", response_model=list[WordSearchResult])
def find_words(
    user: CurrentUser,
    db: DB,
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    include_family: bool = True,
    parts: Annotated[list[PartOfSpeech] | None, Query()] = None,
    forms: Annotated[list[VerbForm] | None, Query()] = None,
) -> list[WordSearchResult]:
    query = normalise_word(q)
    if not query:
        raise HTTPException(422, "Enter a word to search.")
    response.headers["Cache-Control"] = "no-store"
    try:
        entries = search_dictionary(
            query,
            include_family,
            parts if parts is not None else ["noun", "verb", "adjective", "adverb"],
            forms if forms is not None else ["V1", "V2", "V3"],
        )
    except LookupError:
        raise HTTPException(
            503, "Dictionary is unavailable. Please try again later."
        ) from None
    normalized = {normalise_word(entry.word) for entry in entries}
    saved = (
        set(
            db.scalars(
                select(Word.normalised_word).where(
                    Word.user_id == user.id,
                    Word.normalised_word.in_(normalized),
                )
            )
        )
        if normalized
        else set()
    )
    return [
        WordSearchResult(
            **entry.model_dump(),
            saved=normalise_word(entry.word) in saved,
        )
        for entry in entries
    ]


@router.post("/words", status_code=201, response_model=WordCreated)
def create_word(
    body: CreateWord, response: Response, db: DB, user: CurrentUser
) -> WordCreated:
    lock_account(db, user)
    word = Word(
        user_id=user.id,
        word=body.word,
        english_explanation=body.english_explanation,
        example_sentence=body.example_sentence,
    )
    db.add(word)
    try:
        db.flush()
        db.add(ReviewState(word_id=word.id, due_at=datetime.now(UTC)))
        db.commit()
    except IntegrityError:
        db.rollback()
        # Only the per-owner normalized duplicate is a client conflict.
        duplicate = db.scalar(
            select(Word.id).where(
                Word.user_id == user.id,
                Word.normalised_word == normalise_word(body.word),
            )
        )
        if duplicate is None:
            raise
        raise HTTPException(409, "Word already exists") from None
    response.headers["Cache-Control"] = "no-store"
    return WordCreated(
        id=word.id,
        word=word.word,
        english_explanation=word.english_explanation,
        example_sentence=word.example_sentence,
    )


@router.get("/reviews/next", response_model=list[ReviewItem])
def next_reviews(
    response: Response,
    db: DB,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 1,
) -> list[ReviewItem]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    remaining = remaining_daily_reviews(db, user, now)
    if remaining == 0:
        return []
    # Read the answer only to redact hints; never serialize it in the prompt.
    rows = db.execute(
        select(Word.id, Word.word, Word.english_explanation, Word.example_sentence)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.user_id == user.id, ReviewState.due_at <= now)
        .order_by(ReviewState.due_at, Word.id)
        .limit(min(limit, remaining))
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


@router.get("/reviews/summary")
def review_summary(response: Response, db: DB, user: CurrentUser) -> dict[str, int]:
    response.headers["Cache-Control"] = "no-store"
    return review_totals(db, user, datetime.now(UTC))


@router.get("/reviews/preparation")
def review_preparation(
    response: Response,
    db: DB,
    user: CurrentUser,
    selection: Annotated[ReviewSelection, Query()],
) -> dict[str, int]:
    response.headers["Cache-Control"] = "no-store"
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
        "count": min(matching, totals["daily_remaining"], 50),
        "matching_count": matching,
    }


@router.get("/reviews/session", response_model=list[SessionItem | TypingSessionItem])
def review_session(
    response: Response,
    db: DB,
    user: CurrentUser,
    selection: Annotated[ReviewSelection, Query()],
) -> list[TypingSessionItem]:
    response.headers["Cache-Control"] = "no-store"
    now = datetime.now(UTC)
    remaining = min(50, remaining_daily_reviews(db, user, now))
    rows = db.execute(selected_words(user, now, selection).limit(remaining)).all()
    if not rows:
        return []
    # Infer POS once per saved word; all prompts share these cached profiles.
    bank = (
        list(
            db.scalars(
                select(Word.word).where(Word.user_id == user.id).order_by(Word.id)
            )
        )
        if selection.answer_mode == "choice"
        else []
    )
    saved_parts = (
        {word: review_parts(word) for word in bank}
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
            prompt_sentence=prompt_sentence(
                word.example_sentence, word.english_explanation, word.word
            ),
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


@router.post("/reviews/{word_id}/choices", response_model=SessionItem)
def word_choices(
    word_id: uuid.UUID,
    body: ChoiceRequest,
    response: Response,
    db: DB,
    user: CurrentUser,
) -> SessionItem:
    """Reveal D16 options only after an explicit switch to multiple choice."""
    pair = db.execute(
        select(Word, ReviewState)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.id == word_id, Word.user_id == user.id)
    ).first()
    if pair is None:
        raise HTTPException(404, "Review item not found")
    word, state = pair
    now = datetime.now(UTC)
    if not valid_ticket(body.review_token, user.id, state, body.attempt_id, now):
        raise HTTPException(
            409, "Review session expired or changed. Start a new review."
        )
    if remaining_daily_reviews(db, user, now) == 0:
        raise HTTPException(409, "Daily review cap reached")
    bank = db.scalars(
        select(Word.word).where(Word.user_id == user.id).order_by(Word.id)
    )
    response.headers["Cache-Control"] = "no-store"
    return SessionItem(
        word_id=word.id,
        attempt_id=body.attempt_id,
        review_token=body.review_token,
        prompt_sentence=prompt_sentence(
            word.example_sentence, word.english_explanation, word.word
        ),
        english_explanation=mask_target(word.english_explanation, word.word),
        example_sentence=mask_target(word.example_sentence, word.word)
        if word.example_sentence
        else None,
        choices=review_options(
            word.word, {value: review_parts(value) for value in bank}
        ),
    )


@router.post("/reviews/{word_id}/answer", response_model=AnswerResult)
def submit_answer(
    word_id: uuid.UUID, body: AnswerInput, response: Response, db: DB, user: CurrentUser
) -> AnswerResult:
    lock_account(db, user)
    pair = db.execute(
        select(Word, ReviewState)
        .join(ReviewState, ReviewState.word_id == Word.id)
        .where(Word.id == word_id, Word.user_id == user.id)
        .with_for_update()
    ).first()
    if pair is None:
        raise HTTPException(404, "Review item not found")
    word, state = pair
    if body.attempt_id is not None:
        previous = db.get(ReviewAttempt, body.attempt_id)
        if previous is not None:
            if previous.user_id != user.id or previous.word_id != word.id:
                raise HTTPException(409, "Submission identifier unavailable")
            if (
                previous.typed_answer != body.typed_answer
                or previous.time_taken_ms != body.time_taken_ms
            ):
                raise HTTPException(409, "Submission payload changed")
            response.headers["Cache-Control"] = "no-store"
            return AnswerResult(
                attempt_id=previous.id,
                result=previous.result,
                correct_word=word.word,
                next_due_at=state.due_at,
            )
    now = datetime.now(UTC)
    if body.review_token is not None and not valid_ticket(
        body.review_token, user.id, state, body.attempt_id, now
    ):
        raise HTTPException(
            409, "Review session expired or changed. Start a new review."
        )
    if body.review_token is None and state.due_at > now:
        raise HTTPException(409, "Review item is not due")
    if remaining_daily_reviews(db, user, now) == 0:
        raise HTTPException(409, "Daily review cap reached")
    correct = answer_matches(body.typed_answer, word.word)
    result: Literal["correct", "incorrect"] = "correct" if correct else "incorrect"
    attempt = ReviewAttempt(
        id=body.attempt_id or uuid.uuid4(),
        word_id=word.id,
        user_id=user.id,
        typed_answer=body.typed_answer,
        result=result,
        reviewed_at=now,
        time_taken_ms=body.time_taken_ms,
    )
    db.add(attempt)
    schedule_review(state, correct, now)
    db.commit()
    response.headers["Cache-Control"] = "no-store"
    return AnswerResult(
        attempt_id=attempt.id,
        result=result,
        correct_word=word.word,
        next_due_at=state.due_at,
    )


@router.delete("/account", status_code=204)
def delete_account(response: Response, db: DB, user: CurrentUser) -> None:
    lock_account(db, user)
    # The trigger permits erasure only after this marker, in the same transaction.
    user.deleted_at = datetime.now(UTC)
    db.flush()
    word_ids = select(Word.id).where(Word.user_id == user.id)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(ReviewAttempt).where(ReviewAttempt.user_id == user.id))
    db.execute(delete(ReviewState).where(ReviewState.word_id.in_(word_ids)))
    db.execute(delete(Word).where(Word.user_id == user.id))
    db.delete(user)
    db.commit()
    response.delete_cookie(
        COOKIE,
        path="/api/v1/auth",
        httponly=True,
        secure=get_settings().auth_cookie_secure,
        samesite="strict",
    )
    response.headers["Cache-Control"] = "no-store"
