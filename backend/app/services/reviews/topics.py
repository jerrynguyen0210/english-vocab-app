"""Exact cosine search over the authenticated user's persisted word vectors."""

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ReviewState, User, Word
from app.services.embeddings import (
    embed_texts,
    model_key,
    normalized_vectors,
    text_hash,
    word_text,
)
from app.services.errors import TopicIndexPending, TopicSearchUnavailable


def topic_words(
    db: Session, user: User, topic: str
) -> tuple[list[tuple[Word, ReviewState]], int]:
    rows = [
        (word, state)
        for word, state in db.execute(
            select(Word, ReviewState)
            .join(ReviewState, ReviewState.word_id == Word.id)
            .where(Word.user_id == user.id)
            .order_by(Word.id)
        ).all()
    ]
    if not rows:
        return [], 0
    key = model_key()
    if any(
        word.embedding_model != key
        or word.embedding_vector is None
        or word.embedding_hash != text_hash(word_text(word))
        for word, _ in rows
    ):
        raise TopicIndexPending(
            "Your word bank is being prepared for topic search. Please try again shortly."
        )
    vectors = normalized_vectors([word.embedding_vector for word, _ in rows], len(rows))
    query = embed_texts([topic])[0]
    matrix = np.asarray(vectors)
    if matrix.shape[1] != len(query):
        raise TopicSearchUnavailable(
            "Topic search model changed. Reindex your word bank before searching."
        )
    scores = matrix @ np.asarray(query)
    # Stable ties follow word ID, so preparation and session order agree.
    indices = np.argsort(-scores, kind="stable")
    matching = [
        int(i)
        for i in indices
        if scores[i] >= get_settings().topic_similarity_threshold
    ]
    return [rows[i] for i in matching[:10]], len(matching)
