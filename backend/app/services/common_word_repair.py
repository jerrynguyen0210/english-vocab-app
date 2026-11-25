"""Repair invalid or missing bank content without replacing words or history."""

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError
from sqlalchemy import Engine, select, update

from app.core.config import Settings
from app.llm.openrouter_common_bank import repair_bank_words
from app.llm.openrouter_review import ReviewError
from app.models import CommonWord
from app.schemas.common_word_bank import GeneratedBankWord

CONTENT_FIELDS = ("part_of_speech", "english_explanation", "example_sentence", "ipa")


def content_issues(row: Mapping[str, Any]) -> set[str]:
    values = {field: row[field] for field in ("word", *CONTENT_FIELDS)}
    issues: set[str] = set()
    try:
        GeneratedBankWord.model_validate(values)
    except ValidationError as error:
        issues.update(str(item["loc"][0]) for item in error.errors())
    if not row["ipa"] or not row["ipa"].strip():
        issues.add("ipa")
    return issues


def repair_bank(
    engine: Engine,
    settings: Settings,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Save each validated batch independently; failed batches can be retried.

    Compare all original content before updating so concurrent edits are preserved.
    Structural problems (duplicates, normalization and timestamps) need manual review.
    """
    with engine.connect() as connection:
        rows = list(
            connection.execute(
                select(CommonWord.__table__).order_by(CommonWord.id)
            ).mappings()
        )
    candidates = [(dict(row), content_issues(dict(row))) for row in rows]
    candidates = [
        (row, issues) for row, issues in candidates if issues and "word" not in issues
    ]
    if not candidates:
        return 0
    if (
        not settings.openrouter_api_key.get_secret_value().strip()
        or not settings.openrouter_model.strip()
    ):
        raise ValueError(
            "Configure private OPENROUTER settings before repairing content"
        )
    saved = 0
    for offset in range(0, len(candidates), 20):
        batch = candidates[offset : offset + 20]
        generated = repair_bank_words(
            [
                {field: row[field] for field in ("word", *CONTENT_FIELDS)}
                for row, _ in batch
            ],
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key.get_secret_value(),
            base_url=settings.openrouter_url,
            timeout=settings.openrouter_timeout_seconds,
        )
        # Validate again at the persistence boundary, including count and word identity.
        validated = [GeneratedBankWord.model_validate(entry) for entry in generated]
        if len(validated) != len(batch) or any(
            entry.word != row["word"] or entry.ipa is None
            for (row, _), entry in zip(batch, validated)
        ):
            raise ReviewError("Invalid vocabulary repair response.", "invalid_response")
        with engine.begin() as connection:
            for (row, issues), entry in zip(batch, validated):
                conditions = [CommonWord.id == row["id"]]
                conditions.extend(
                    getattr(CommonWord, field) == row[field]
                    for field in ("word", *CONTENT_FIELDS)
                )
                result = connection.execute(
                    update(CommonWord)
                    .where(*conditions)
                    .values(**{field: getattr(entry, field) for field in issues})
                )
                saved += result.rowcount
        if progress:
            progress(saved, len(candidates))
    return saved
