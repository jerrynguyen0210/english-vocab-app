"""HTTP polling survives client timeouts and never duplicates generation."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import CommonPracticeBatch, CommonPracticeQuestion, CommonWord, User
from app.schemas.common_words import GeneratedCommonQuestion
from app.services.common_batches import process_one
from app.services.common_words import get_batch
from app.services.errors import CommonGenerationUnavailable

START = "/api/v1/common-words/batches"


@pytest.fixture(autouse=True)
def bank(api):
    _, db, *_ = api
    db.add_all(
        [
            CommonWord(
                word=f"word{i}",
                normalised_word=f"word{i}",
                part_of_speech="noun",
                english_explanation=f"meaning{i}",
            )
            for i in range(20)
        ]
    )
    db.commit()


@pytest.fixture
def generator(monkeypatch):
    calls = []

    def generate(words, **kwargs):
        calls.append(words)
        return [
            GeneratedCommonQuestion(
                common_word_id=w.id,
                question=f"What is {w.word}?",
                choices=[w.english_explanation, "other", "another", "different"],
                correct_index=0,
            )
            for w in words
        ]

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    return calls


def start(api):
    client, _, owner, *_ = api
    response = client.post(START, headers=owner)
    assert response.status_code == 202, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def status(api, batch_id):
    client, _, owner, *_ = api
    return client.get(f"{START}/{batch_id}", headers=owner)


def test_resume_queued_and_ready_batch_without_duplicate_generation(api, generator):
    _, db, *_ = api
    queued = start(api)
    assert queued["status"] == "pending" and queued["questions"] == []
    assert start(api)["id"] == queued["id"]
    assert not generator
    assert process_one(db.get_bind())
    ready = status(api, queued["id"])
    assert ready.status_code == 200
    assert ready.headers["cache-control"] == "no-store"
    assert ready.json()["status"] == "ready"
    assert len(ready.json()["questions"]) == 10
    assert all("correctIndex" not in q for q in ready.json()["questions"])
    assert start(api) == ready.json()
    assert not process_one(db.get_bind())
    assert len(generator) == 1


def test_resume_returns_only_unanswered_questions_and_next_batch_after_answers(
    api, generator
):
    client, db, owner, *_ = api
    queued = start(api)
    process_one(db.get_bind())
    questions = status(api, queued["id"]).json()["questions"]
    for question in questions:
        assert (
            client.post(
                f"/api/v1/common-words/questions/{question['id']}/answer",
                headers=owner,
                json={"selected_index": 0},
            ).status_code
            == 200
        )
        remaining = start(api)
        if question != questions[-1]:
            assert remaining["id"] == queued["id"]
            assert question["id"] not in [q["id"] for q in remaining["questions"]]
    assert remaining["id"] != queued["id"]
    assert remaining["status"] == "pending"


def test_failed_generation_is_terminal_until_explicit_retry(api, monkeypatch):
    _, db, *_ = api

    def fail(*args, **kwargs):
        raise CommonGenerationUnavailable("Private provider details")

    monkeypatch.setattr("app.services.common_batches.get_batch", fail)
    queued = start(api)
    process_one(db.get_bind())
    response = status(api, queued["id"])
    assert response.json()["status"] == "failed"
    assert "Private" not in response.text
    assert db.scalar(select(func.count()).select_from(CommonPracticeQuestion)) == 0
    assert not process_one(db.get_bind())
    assert start(api)["id"] != queued["id"]


def test_generation_remains_resumable_while_worker_is_running(
    api, generator, monkeypatch
):
    _, db, *_ = api
    queued = start(api)

    def during_generation(session, user, *, batch_id):
        assert status(api, batch_id).json()["status"] == "generating"
        assert start(api)["id"] == str(batch_id)
        return get_batch(session, user, batch_id=batch_id)

    monkeypatch.setattr("app.services.common_batches.get_batch", during_generation)
    process_one(db.get_bind())
    assert status(api, queued["id"]).json()["status"] == "ready"
    assert len(generator) == 1


def test_expired_worker_cannot_persist_after_retry(api, generator):
    _, db, *_ = api
    queued = start(api)
    batch = db.scalar(select(CommonPracticeBatch))
    batch.status = "generating"
    batch.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert status(api, queued["id"]).json()["status"] == "failed"
    new_batch = start(api)
    user = db.get(User, batch.user_id)
    with pytest.raises(CommonGenerationUnavailable):
        get_batch(db, user, batch_id=uuid.UUID(queued["id"]))
    db.rollback()
    assert db.scalar(select(func.count()).select_from(CommonPracticeQuestion)) == 0
    process_one(db.get_bind())
    assert status(api, new_batch["id"]).json()["status"] == "ready"


def test_polling_is_owned_and_account_erasure_removes_batch(api, generator):
    client, db, owner, other, *_ = api
    queued = start(api)
    assert client.get(f"{START}/{queued['id']}", headers=other).status_code == 404
    assert client.get(f"{START}/{queued['id']}").status_code == 401
    assert client.post(START).status_code == 401
    assert client.delete("/api/v1/account", headers=owner).status_code == 204
    assert not process_one(db.get_bind())
    assert db.scalar(select(func.count()).select_from(CommonPracticeBatch)) == 0


def test_late_worker_cannot_overwrite_replacement_batch(api, generator, monkeypatch):
    from app.services import common_words

    _, db, *_ = api
    queued = start(api)
    generate = common_words.generate_common_questions
    replacement = []

    def expire_during_generation(words, **kwargs):
        batch = db.scalar(select(CommonPracticeBatch))
        batch.available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        replacement.append(start(api))
        return generate(words, **kwargs)

    monkeypatch.setattr(
        common_words, "generate_common_questions", expire_during_generation
    )
    process_one(db.get_bind())
    assert replacement[0]["id"] != queued["id"]
    assert status(api, replacement[0]["id"]).json()["status"] == "pending"
    assert db.scalar(select(func.count()).select_from(CommonPracticeQuestion)) == 0


def test_concurrent_starts_share_one_batch_on_postgres(api, generator):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    from app.services.common_batches import start_batch

    client, db, owner, *_ = api
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Concurrent account locking requires PostgreSQL")
    user_id = uuid.UUID(client.get("/api/v1/auth/me", headers=owner).json()["id"])
    db.commit()
    barrier = Barrier(2)
    engine = db.get_bind()

    def submit():
        with Session(engine) as session:
            user = session.get(User, user_id)
            barrier.wait(timeout=5)
            return start_batch(session, user)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0].id == results[1].id
    assert not generator
