"""Semantic review ranking, persistent indexing, ownership and scheduling."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ReviewAttempt, ReviewState, Word
from app.services import embeddings
from app.services.errors import TopicSearchUnavailable

from .helpers import create


def index(db, monkeypatch):
    calls = []

    def embed(texts, **kwargs):
        calls.extend(texts)
        return [
            [1.0, 0.0] if not text.startswith("unrelated") else [0.0, 1.0]
            for text in texts
        ]

    monkeypatch.setattr(embeddings, "embed_texts", embed)
    assert embeddings.index_batch(db.get_bind()) > 0
    db.expire_all()
    return calls


def test_topic_ranks_ten_own_words_and_answers_use_existing_tickets(api, monkeypatch):
    client, db, owner, other, _ = api
    ids = [create(client, owner, f"related{i}").json()["id"] for i in range(12)]
    create(client, owner, "unrelated")
    foreign = create(client, other, "private").json()["id"]
    for word_id in ids:
        db.get(ReviewState, uuid.UUID(word_id)).due_at = datetime.now(UTC) + timedelta(
            days=10
        )
    db.commit()
    indexed = index(db, monkeypatch)
    assert len(indexed) == 14
    assert embeddings.index_batch(db.get_bind()) == 0  # no repeated word embeddings
    queries = []

    def query(texts):
        queries.extend(texts)
        return [[1.0, 0.0]]

    monkeypatch.setattr("app.services.reviews.topics.embed_texts", query)
    params = {"source": "topic", "topic": "Workplace communication"}
    response = client.get("/api/v1/reviews/preparation", params=params, headers=owner)
    assert response.status_code == 200, response.text
    assert response.json()["count"] == 10
    assert response.json()["matching_count"] == 12
    assert "word" not in response.json()
    assert response.headers["cache-control"] == "no-store"
    items = client.get("/api/v1/reviews/session", params=params, headers=owner).json()
    assert [p["word_id"] for p in items] == sorted(ids)[:10]
    assert foreign not in [p["word_id"] for p in items]
    assert len(queries) == 2
    assert all("choices" not in item and "word" not in item for item in items)
    item = items[0]
    word = db.get(Word, uuid.UUID(item["word_id"]))
    path = f"/api/v1/reviews/{word.id}/answer"
    body = {
        "attempt_id": item["attempt_id"],
        "review_token": item["review_token"],
        "typed_answer": word.word,
        "time_taken_ms": 100,
    }
    assert client.post(path, headers=other, json=body).status_code == 404
    assert client.post(path, headers=owner, json=body).json()["result"] == "correct"
    assert client.post(path, headers=owner, json=body).status_code == 200
    assert len(list(db.scalars(select(ReviewAttempt)))) == 1
    assert db.get(ReviewState, word.id).repetitions == 1
    choices = client.get(
        "/api/v1/reviews/session",
        params={**params, "answer_mode": "choice"},
        headers=owner,
    )
    assert choices.status_code == 200
    assert len(choices.json()[0]["choices"]) == 4
    assert client.delete("/api/v1/account", headers=owner).status_code == 204
    assert db.get(Word, word.id) is None


def test_topic_validation_pending_and_provider_failures(api, monkeypatch):
    client, db, owner, other, _ = api
    for topic in ["", "   ", "a" * 201]:
        assert (
            client.get(
                "/api/v1/reviews/preparation",
                params={"source": "topic", "topic": topic},
                headers=owner,
            ).status_code
            == 422
        )
    assert (
        client.get("/api/v1/reviews/session?source=topic&topic=work").status_code == 401
    )
    create(client, other, "foreign-pending")
    # Another user's pending index cannot block or enter an empty bank.
    assert (
        client.get(
            "/api/v1/reviews/session?source=topic&topic=work", headers=owner
        ).json()
        == []
    )
    create(client, owner)
    path = "/api/v1/reviews/preparation?source=topic&topic=work"
    assert client.get(path, headers=owner).status_code == 409
    assert "being prepared" in client.get(path, headers=owner).json()["detail"]
    index(db, monkeypatch)

    def offline(_):
        raise TopicSearchUnavailable("Topic search is unavailable. Please try again.")

    monkeypatch.setattr("app.services.reviews.topics.embed_texts", offline)
    assert client.get(path, headers=owner).status_code == 503

    monkeypatch.setattr(
        "app.services.reviews.topics.embed_texts", lambda _: [[0.0, 1.0]]
    )
    assert client.get(path, headers=owner).json()["count"] == 0
    monkeypatch.setattr(
        "app.services.reviews.topics.embed_texts", lambda _: [[1.0, 0.0, 0.0]]
    )
    assert client.get(path, headers=owner).status_code == 503


def test_topic_order_is_descending_similarity_not_save_order(api, monkeypatch):
    client, db, owner, _, _ = api
    vectors = {
        "low": [0.6, 0.8],
        "best": [1.0, 0.0],
        "weak": [0.0, 1.0],
        "middle": [0.8, 0.6],
    }
    ids = {name: create(client, owner, name).json()["id"] for name in vectors}
    monkeypatch.setattr(
        embeddings,
        "embed_texts",
        lambda texts, **kw: [vectors[text.splitlines()[0]] for text in texts],
    )
    embeddings.index_batch(db.get_bind())
    db.expire_all()
    monkeypatch.setattr(
        "app.services.reviews.topics.embed_texts", lambda _: [[1.0, 0.0]]
    )
    response = client.get(
        "/api/v1/reviews/session?source=topic&topic=work", headers=owner
    )
    assert response.status_code == 200
    assert [item["word_id"] for item in response.json()] == [
        ids["best"],
        ids["middle"],
        ids["low"],
    ]


def test_index_recovers_from_outage_reindexes_changed_content_and_model(
    api, monkeypatch
):
    client, db, owner, _, _ = api
    word_id = uuid.UUID(create(client, owner).json()["id"])

    def fail(_, **kwargs):
        raise TopicSearchUnavailable("offline")

    monkeypatch.setattr(embeddings, "embed_texts", fail)
    with pytest.raises(TopicSearchUnavailable):
        embeddings.index_batch(db.get_bind())
    assert db.get(Word, word_id).embedding_hash is None
    index(db, monkeypatch)
    word = db.get(Word, word_id)
    first_hash = word.embedding_hash
    word.english_explanation = "A different meaning"
    db.commit()
    assert word.embedding_vector is None
    index(db, monkeypatch)
    assert db.get(Word, word_id).embedding_hash != first_hash
    monkeypatch.setenv("EMBEDDING_REVISION", "new-weights")
    get_settings.cache_clear()
    assert (
        client.get(
            "/api/v1/reviews/preparation?source=topic&topic=work", headers=owner
        ).status_code
        == 409
    )
    index(db, monkeypatch)
    assert db.get(Word, word_id).embedding_model.endswith("@new-weights")


def test_index_does_not_restore_deleted_or_stale_words(api, monkeypatch):
    client, db, owner, _, _ = api
    word_id = uuid.UUID(create(client, owner).json()["id"])
    engine = db.get_bind()

    def during_generation(texts, **kwargs):
        with Session(engine) as other_db:
            other_db.get(Word, word_id).english_explanation = "Changed during embedding"
            other_db.commit()
        return [[1.0, 0.0]]

    monkeypatch.setattr(embeddings, "embed_texts", during_generation)
    assert embeddings.index_batch(engine) == 1
    db.expire_all()
    assert db.get(Word, word_id).embedding_vector is None

    def deleted_during_generation(texts, **kwargs):
        assert client.delete("/api/v1/account", headers=owner).status_code == 204
        return [[1.0, 0.0]]

    monkeypatch.setattr(embeddings, "embed_texts", deleted_during_generation)
    assert embeddings.index_batch(engine) == 1
    assert db.get(Word, word_id) is None
