"""Read and explicitly delete shared Common vocabulary for backend operators."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Engine, delete, func, select
from sqlalchemy.orm import Session

from app.core.text import normalise_word
from app.models import CommonPracticeQuestion, CommonWord, UserCommonWordProgress


@dataclass(frozen=True)
class BankInspection:
    words: int
    counts: dict[str, int]
    samples: dict[str, list[str]]


def inspect_bank(engine: Engine, sample_limit: int = 10) -> BankInspection:
    """Read bank quality findings without changing words or learning history.

    Duplicate counts count groups; missing fields and mismatches count rows.
    Keep sample output bounded while scanning every bank entry.
    """
    if sample_limit < 1:
        raise ValueError("Sample limit must be positive")
    required = (
        "word", "normalised_word", "part_of_speech", "english_explanation",
        "created_at",
    )
    optional = ("example_sentence", "ipa")
    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}

    def record(category: str, detail: str) -> None:
        counts[category] = counts.get(category, 0) + 1
        examples = samples.setdefault(category, [])
        if len(examples) < sample_limit:
            examples.append(detail)

    # Track the first row and count for each key, retaining bounded group samples.
    groups: dict[str, dict[str, tuple[int, list[str]]]] = {
        "Duplicate normalized words": {},
        "Duplicate stored normalization keys": {},
    }
    total = 0
    with engine.connect() as connection:
        rows = connection.execution_options(yield_per=500).execute(
            select(CommonWord.__table__).order_by(CommonWord.id)
        ).mappings()
        for row in rows:
            total += 1
            label = f"ID {row['id']}, word {row['word']!r}"
            for field in (*required, *optional):
                value = row[field]
                if value is None or (isinstance(value, str) and not value.strip()):
                    prefix = "Missing required" if field in required else "Missing optional"
                    record(f"{prefix}: {field}", label)
            normalized = normalise_word(row["word"] or "")
            stored = row["normalised_word"]
            if normalized and stored != normalized:
                record(
                    "Inconsistent normalization",
                    f"{label}; stored {stored!r}, expected {normalized!r}",
                )
            for category, key in (
                ("Duplicate normalized words", normalized),
                ("Duplicate stored normalization keys", stored),
            ):
                if not key or not key.strip():
                    continue
                count, ids = groups[category].get(key, (0, []))
                if len(ids) < sample_limit:
                    ids.append(str(row["id"]))
                groups[category][key] = (count + 1, ids)
    for category, entries in groups.items():
        for key, (count, ids) in entries.items():
            if count > 1:
                record(category, f"{key!r}: {count} rows; sample IDs: {', '.join(ids)}")
    return BankInspection(total, counts, samples)


@dataclass(frozen=True)
class BankEntry:
    id: UUID
    word: str
    part_of_speech: str
    meaning: str
    example: str | None
    ipa: str | None
    created_at: datetime

    @classmethod
    def from_word(cls, word: CommonWord) -> "BankEntry":
        return cls(
            word.id,
            word.word,
            word.part_of_speech,
            word.english_explanation,
            word.example_sentence,
            word.ipa,
            word.created_at,
        )


@dataclass(frozen=True)
class DeletedContent:
    words: int = 0
    questions: int = 0
    progress: int = 0


def bank_summary(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return {
            "words": connection.scalar(select(func.count()).select_from(CommonWord))
            or 0,
            "questions": connection.scalar(
                select(func.count()).select_from(CommonPracticeQuestion)
            )
            or 0,
            "progress": connection.scalar(
                select(func.count()).select_from(UserCommonWordProgress)
            )
            or 0,
            "learned": connection.scalar(
                select(func.count())
                .select_from(UserCommonWordProgress)
                .where(UserCommonWordProgress.learned_at.is_not(None))
            )
            or 0,
        }


def latest_words(engine: Engine, limit: int = 10) -> list[BankEntry]:
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100")
    with Session(engine) as db:
        return [
            BankEntry.from_word(word)
            for word in db.scalars(
                select(CommonWord)
                .order_by(CommonWord.created_at.desc(), CommonWord.id.desc())
                .limit(limit)
            )
        ]


def browse_words(
    engine: Engine, search: str = "", after: str | None = None
) -> tuple[list[BankEntry], str | None]:
    from app.core.text import normalise_word

    statement = select(CommonWord).order_by(CommonWord.normalised_word).limit(11)
    if search:
        statement = statement.where(
            CommonWord.normalised_word.contains(normalise_word(search), autoescape=True)
        )
    if after is not None:
        statement = statement.where(CommonWord.normalised_word > after)
    with Session(engine) as db:
        words = list(db.scalars(statement))
        cursor = words[9].normalised_word if len(words) > 10 else None
        return [BankEntry.from_word(word) for word in words[:10]], cursor


def find_word(engine: Engine, value: str) -> BankEntry | None:
    from app.core.text import normalise_word

    try:
        word_id = UUID(value.strip())
        statement = select(CommonWord).where(CommonWord.id == word_id)
    except ValueError:
        statement = select(CommonWord).where(
            CommonWord.normalised_word == normalise_word(value)
        )
    with Session(engine) as db:
        word = db.scalar(statement)
        return BankEntry.from_word(word) if word is not None else None


def all_word_ids(engine: Engine) -> list[UUID]:
    with engine.connect() as connection:
        return list(connection.scalars(select(CommonWord.id).order_by(CommonWord.id)))


def delete_bank_words(engine: Engine, word_ids: list[UUID]) -> DeletedContent:
    """Delete an explicit snapshot of IDs and dependencies in one transaction.

    Saved recall words are independent and never touched. IDs added after an
    operator preview/confirmation are outside the snapshot and remain intact.
    """
    word_ids = list(dict.fromkeys(word_ids))
    words = questions = progress = 0
    with engine.begin() as connection:
        for offset in range(0, len(word_ids), 100):
            ids = list(
                connection.scalars(
                    select(CommonWord.id)
                    .where(CommonWord.id.in_(word_ids[offset : offset + 100]))
                    .order_by(CommonWord.id)
                    .with_for_update()
                )
            )
            if not ids:
                continue
            questions += connection.execute(
                delete(CommonPracticeQuestion).where(
                    CommonPracticeQuestion.common_word_id.in_(ids)
                )
            ).rowcount
            progress += connection.execute(
                delete(UserCommonWordProgress).where(
                    UserCommonWordProgress.common_word_id.in_(ids)
                )
            ).rowcount
            words += connection.execute(
                delete(CommonWord).where(CommonWord.id.in_(ids))
            ).rowcount
    return DeletedContent(words=words, questions=questions, progress=progress)
