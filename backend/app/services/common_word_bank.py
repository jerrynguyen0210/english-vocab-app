"""Append an operator-selected number of LLM-generated words to the shared SQL bank."""

from collections.abc import Callable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import Engine, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.text import normalise_word
from app.llm.openrouter_common_bank import generate_bank_words
from app.llm.openrouter_review import ReviewError
from app.models import CommonWord
from app.schemas.common_word_bank import GeneratedBankBatch


class BankGenerationStopped(Exception):
    def __init__(self, inserted: int, requested: int, reason: str) -> None:
        self.inserted = inserted
        self.requested = requested
        super().__init__(
            f"{reason} Saved {inserted} of {requested} new words; {requested - inserted} remain."
        )


def populate_bank(
    engine: Engine,
    count: int,
    settings: Settings,
    *,
    batch_size: int = 20,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    if type(count) is not int or count < 1 or not 1 <= batch_size <= 50:
        raise ValueError(
            "Count must be positive and batch size must be between 1 and 50"
        )
    if (
        not settings.openrouter_api_key.get_secret_value().strip()
        or not settings.openrouter_model.strip()
    ):
        raise ValueError(
            "Configure OPENROUTER_API_KEY and OPENROUTER_MODEL in the private backend environment"
        )
    dialect = engine.dialect.name
    if dialect not in {"sqlite", "postgresql"}:
        raise ValueError("Common bank generation supports SQLite and PostgreSQL")
    insert = postgres_insert if dialect == "postgresql" else sqlite_insert
    inserted, stalled = 0, 0
    try:
        while inserted < count:
            # Read exclusions in a short transaction; never hold it during LLM work.
            with engine.connect() as connection:
                existing = set(connection.scalars(select(CommonWord.normalised_word)))
            requested = min(batch_size, count - inserted)
            generated = generate_bank_words(
                requested,
                sorted(existing),
                model=settings.openrouter_model,
                api_key=settings.openrouter_api_key.get_secret_value(),
                base_url=settings.openrouter_url,
                timeout=settings.openrouter_timeout_seconds,
            )
            candidates = GeneratedBankBatch(words=generated).words
            if len(candidates) > requested:
                raise ValueError("Too many generated words")
            added = 0
            with engine.begin() as connection:
                for candidate in candidates:
                    normalized = normalise_word(candidate.word)
                    if normalized in existing:
                        continue
                    existing.add(normalized)
                    statement = (
                        insert(CommonWord)
                        .values(
                            id=uuid5(
                                NAMESPACE_URL,
                                "wordrecall/common-bank/llm/" + normalized,
                            ),
                            word=candidate.word,
                            normalised_word=normalized,
                            part_of_speech=candidate.part_of_speech,
                            english_explanation=candidate.english_explanation,
                            example_sentence=candidate.example_sentence,
                            ipa=candidate.ipa,
                        )
                        .on_conflict_do_nothing(index_elements=["normalised_word"])
                        .returning(CommonWord.id)
                    )
                    if connection.scalar(statement) is not None:
                        added += 1
            inserted += added
            if progress is not None:
                progress(inserted, count)
            stalled = stalled + 1 if added == 0 else 0
            if stalled >= 3:
                raise BankGenerationStopped(
                    inserted,
                    count,
                    "The model returned no new words in three consecutive batches.",
                )
    except ReviewError as error:
        reason = {
            "provider_http": "The LLM provider rejected the request.",
            "provider_connection": "The LLM provider connection failed.",
            "invalid_response": "The LLM response failed output validation.",
            "invalid_input": "LLM generation settings or input are invalid.",
        }.get(error.category, "LLM generation failed.")
        if error.diagnostic:
            reason += " " + error.diagnostic
        raise BankGenerationStopped(inserted, count, reason) from None
    except ValueError:
        raise BankGenerationStopped(
            inserted,
            count,
            "LLM generation or output validation failed. Check the configured model and retry.",
        ) from None
    except SQLAlchemyError:
        raise BankGenerationStopped(
            inserted,
            count,
            "Database write/read failed. Verify database access and apply migrations before retrying.",
        ) from None
    return inserted
