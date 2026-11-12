"""Validated Ollama embeddings and persistent, restartable word indexing."""

import hashlib
import json
from urllib.error import URLError
from urllib.request import Request, urlopen

import numpy as np
from sqlalchemy import Engine, or_, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Word
from app.services.errors import TopicSearchUnavailable


def model_key() -> str:
    settings = get_settings()
    return f"{settings.embedding_model}@{settings.embedding_revision}"


def word_text(word: Word) -> str:
    return f"{word.word}\n{word.english_explanation}\n{word.example_sentence or ''}"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalized_vectors(values: object, count: int) -> list[list[float]]:
    try:
        vectors = np.asarray(values, dtype=np.float64)
        if (
            vectors.ndim != 2
            or vectors.shape[0] != count
            or not 1 <= vectors.shape[1] <= 8192
            or not np.isfinite(vectors).all()
        ):
            raise ValueError()
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        if not np.isfinite(norms).all() or (norms == 0).any():
            raise ValueError()
        return (vectors / norms).tolist()
    except (ValueError, TypeError, OverflowError):
        raise TopicSearchUnavailable(
            "Topic search returned invalid embeddings. Please try again."
        ) from None


def embed_texts(texts: list[str], *, timeout: float | None = None) -> list[list[float]]:
    settings = get_settings()
    request = Request(
        f"{settings.ollama_url.rstrip('/')}/api/embed",
        data=json.dumps({"model": settings.embedding_model, "input": texts}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(
            request, timeout=timeout or settings.embedding_timeout_seconds
        ) as response:
            envelope = json.load(response)
        if not isinstance(envelope, dict):
            raise TypeError()
        return normalized_vectors(envelope.get("embeddings"), len(texts))
    except (URLError, OSError, ValueError, TypeError, UnicodeError):
        # Never expose provider responses, vocabulary or infrastructure details.
        raise TopicSearchUnavailable(
            "Topic search is unavailable. Please try again."
        ) from None


def index_batch(engine: Engine) -> int:
    """Index new/old words in small batches; safe to retry and run concurrently."""
    key = model_key()
    with Session(engine) as db:
        words = list(
            db.scalars(
                select(Word)
                .where(
                    or_(
                        Word.embedding_vector.is_(None),
                        Word.embedding_model.is_(None),
                        Word.embedding_model != key,
                        Word.embedding_hash.is_(None),
                    )
                )
                .order_by(Word.created_at, Word.id)
                .limit(32)
            )
        )
        # Copy data before releasing the database connection for provider work.
        snapshots = [
            (
                word.id,
                word.word,
                word.english_explanation,
                word.example_sentence,
                word_text(word),
            )
            for word in words
        ]
    if not snapshots:
        return 0
    vectors = embed_texts(
        [row[4] for row in snapshots],
        timeout=get_settings().embedding_index_timeout_seconds,
    )
    with Session(engine) as db, db.begin():
        for (word_id, word, meaning, example, text), vector in zip(
            snapshots, vectors, strict=True
        ):
            # An account deletion or edited word must never be resurrected/overwritten.
            db.execute(
                update(Word)
                .where(
                    Word.id == word_id,
                    Word.word == word,
                    Word.english_explanation == meaning,
                    Word.example_sentence == example,
                )
                .values(
                    embedding_vector=vector,
                    embedding_model=key,
                    embedding_hash=text_hash(text),
                )
            )
    return len(snapshots)
