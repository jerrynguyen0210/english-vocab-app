"""Word lookup and atomic creation of words with review state."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.llm.ollama_review import ReviewError, generate_review
from app.models import ReviewState, User, Word
from app.models.word import normalise_word
from app.schemas.words import CreateWord, WordCreated, WordSearchResult
from app.services.accounts import lock_account
from app.services.dictionary import (
    PartOfSpeech,
    VerbForm,
    search_dictionary,
)
from app.services.errors import (
    DictionaryUnavailable,
    InvalidSearch,
    ReviewGenerationUnavailable,
    WordAlreadyExists,
)


def find_words(
    user: User,
    db: Session,
    q: str,
    include_family: bool = True,
    parts: list[PartOfSpeech] | None = None,
    forms: list[VerbForm] | None = None,
) -> list[WordSearchResult]:
    query = normalise_word(q)
    if not query:
        raise InvalidSearch("Enter a word to search.")
    try:
        entries = search_dictionary(
            query,
            include_family,
            parts if parts is not None else ["noun", "verb", "adjective", "adverb"],
            forms if forms is not None else ["V1", "V2", "V3"],
        )
    except LookupError:
        raise DictionaryUnavailable(
            "Dictionary is unavailable. Please try again later."
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


def create_word(body: CreateWord, db: Session, user: User) -> WordCreated:
    # Avoid generation for known duplicates; the database constraint still handles races.
    duplicate = db.scalar(
        select(Word.id).where(
            Word.user_id == user.id,
            Word.normalised_word == normalise_word(body.word),
        )
    )
    if duplicate is not None:
        raise WordAlreadyExists("Word already exists")
    settings = get_settings()
    try:
        generated = generate_review(
            body.word,
            body.english_explanation,
            model=settings.ollama_model,
            base_url=settings.ollama_url,
            timeout=settings.ollama_timeout_seconds,
        )
    except (ReviewError, ValueError):
        db.rollback()
        raise ReviewGenerationUnavailable(
            "Could not generate a review prompt. Word was not saved. Please try again."
        ) from None
    # Acquire the account lock only after the network call; recheck account erasure.
    lock_account(db, user)
    word = Word(
        user_id=user.id,
        word=body.word,
        english_explanation=body.english_explanation,
        example_sentence=body.example_sentence,
        review_prompt=generated["prompt_sentence"],
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
        raise WordAlreadyExists("Word already exists") from None
    return WordCreated(
        id=word.id,
        word=word.word,
        english_explanation=word.english_explanation,
        example_sentence=word.example_sentence,
    )
