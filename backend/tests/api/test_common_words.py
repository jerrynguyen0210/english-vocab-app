"""Authenticated Common bank flows, filtering, queue recovery and account erasure."""

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import func, select

from app.export_user import collect_user_data
from app.llm.openrouter_review import ReviewError
from app.models import CommonWordJob, CommonWordQuestion, ReviewState, User, Word
from app.schemas.common_words import GeneratedCommonWord
from app.services.common_word_worker import claim_job, finish_job, process_one

from .helpers import create

URL = "/api/v1/common-words/batch"


def candidate(word="reliable"):
    return GeneratedCommonWord(
        word=word,
        part_of_speech="adjective",
        explanation="Able to be trusted.",
        example=f"She is {word} today.",
        choices=[
            "Easy to forget",
            "Able to be trusted",
            "Very expensive",
            "Difficult to use",
        ],
        correct_index=1,
    )


def generate(api, monkeypatch, items=None):
    client, db, owner, _, _ = api
    generator = Mock(
        return_value=items if items is not None else [candidate(), candidate("eager")]
    )
    monkeypatch.setattr(
        "app.services.common_word_worker.generate_common_words", generator
    )
    assert client.post(URL, headers=owner, json={}).status_code == 202
    db.rollback()
    assert process_one(db.get_bind())
    db.expire_all()
    return generator


def test_generation_is_async_persistent_and_filtered_to_current_user(api, monkeypatch):
    client, db, owner, other, _ = api
    assert create(client, owner, " ＲELIABLE ").status_code == 201
    assert create(client, other, "eager").status_code == 201
    generator = generate(
        api, monkeypatch, [candidate(), candidate("eager"), candidate("eager")]
    )
    assert db.scalar(select(func.count()).select_from(CommonWordQuestion)) == 1
    response = client.post(URL, headers=owner, json={})
    assert (
        response.status_code == 200 and response.headers["cache-control"] == "no-store"
    )
    assert response.json()["status"] == "ready"
    item = response.json()["questions"][0]
    assert item["word"] == "eager"  # Other accounts' saved words must not exclude mine.
    assert item["correctIndex"] == 1 and item["partOfSpeech"] == "adjective"
    assert len(item["choices"]) == 4
    assert db.scalar(select(func.count()).select_from(Word)) == 2
    assert db.scalar(select(func.count()).select_from(ReviewState)) == 2
    assert db.scalar(select(func.count()).select_from(CommonWordJob)) == 0
    generator.assert_called_once()
    assert (
        "reliable" not in generator.call_args.args[0]
    )  # Saved vocabulary stays local.
    assert client.post(URL, headers=other, json={}).json()["status"] == "pending"
    assert (
        client.post(URL, headers=owner, json={}).json()["questions"][0]["id"]
        == item["id"]
    )
    assert generator.call_count == 1


def test_saved_words_are_rechecked_before_insertion_and_before_serving(
    api, monkeypatch
):
    client, db, owner, _, _ = api
    assert client.post(URL, headers=owner, json={}).status_code == 202
    db.rollback()
    claimed = claim_job(db.get_bind())
    assert create(client, owner, "RELIABLE").status_code == 201
    db.rollback()
    finish_job(db.get_bind(), claimed, [candidate(), candidate("eager")])
    db.expire_all()
    assert [q.word for q in db.scalars(select(CommonWordQuestion))] == ["eager"]
    assert create(client, owner, "eager").status_code == 201
    assert client.post(URL, headers=owner, json={}).json()["status"] == "pending"


def test_saved_word_normalization_deduplication_and_batches_do_not_repeat_loaded_ids(
    api, monkeypatch
):
    client, db, owner, _, _ = api
    generate(api, monkeypatch)
    first = client.post(URL, headers=owner, json={}).json()["questions"]
    ids = [item["id"] for item in first]
    response = client.post(URL, headers=owner, json={"exclude_ids": ids})
    assert response.status_code == 202
    assert response.json()["questions"] == []
    assert response.headers["retry-after"] == "2"
    # Repeated polling queues exactly one durable job, with no direct LLM calls.
    for _ in range(3):
        assert (
            client.post(URL, headers=owner, json={"exclude_ids": ids}).status_code
            == 202
        )
    assert db.scalar(select(func.count()).select_from(CommonWordJob)) == 1
    db.rollback()
    claimed = claim_job(db.get_bind())
    assert set(claimed.excluded_words) == {"reliable", "eager"}
    finish_job(db.get_bind(), claimed, [candidate("patient")])
    response = client.post(URL, headers=owner, json={"exclude_ids": ids})
    assert [q["word"] for q in response.json()["questions"]] == ["patient"]


def test_failure_retries_are_bounded_and_retry_does_not_create_a_job_storm(
    api, monkeypatch
):
    client, db, owner, _, _ = api
    failed = Mock(
        side_effect=ReviewError("private provider body", "provider_connection")
    )
    monkeypatch.setattr("app.services.common_word_worker.generate_common_words", failed)
    client.post(URL, headers=owner, json={})
    owner_id = db.scalar(select(User.id).where(User.email == "owner@example.com"))
    db.rollback()
    for attempt in range(3):
        assert process_one(db.get_bind())
        db.expire_all()
        job = db.get(CommonWordJob, owner_id)
        assert job.attempts == attempt + 1
        assert job.failure_category == "provider_connection"
        if attempt < 2:
            assert job.failed_at is None
            job.available_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
    db.rollback()
    assert not process_one(db.get_bind())
    assert client.post(URL, headers=owner, json={}).json() == {
        "status": "failed",
        "questions": [],
    }
    assert failed.call_count == 3
    job = db.get(CommonWordJob, owner_id)
    job.failed_at = datetime.now(UTC) - timedelta(seconds=61)
    db.commit()
    assert client.post(URL, headers=owner, json={}).status_code == 202
    assert db.get(CommonWordJob, owner_id).attempts == 0


def test_only_saved_or_duplicate_results_do_not_produce_an_empty_success(
    api, monkeypatch
):
    client, db, owner, _, _ = api
    create(client, owner, "reliable")
    generate(api, monkeypatch, [candidate(), candidate()])
    job = db.scalar(select(CommonWordJob))
    assert job.failure_category == "no_new_words" and job.attempts == 1
    assert db.scalar(select(func.count()).select_from(CommonWordQuestion)) == 0
    assert client.post(URL, headers=owner, json={}).status_code == 202


def test_worker_lease_prevents_double_claim_and_discards_stale_results(api):
    client, db, owner, _, _ = api
    client.post(URL, headers=owner, json={})
    db.rollback()
    first = claim_job(db.get_bind())
    assert claim_job(db.get_bind()) is None
    job = db.get(CommonWordJob, first.user_id)
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    second = claim_job(db.get_bind())
    assert second.token != first.token
    finish_job(db.get_bind(), first, [candidate()])
    assert db.scalar(select(func.count()).select_from(CommonWordQuestion)) == 0
    db.rollback()
    finish_job(db.get_bind(), second, [candidate("eager")])
    db.expire_all()
    assert db.scalar(select(CommonWordQuestion.word)) == "eager"


def test_crashed_final_attempt_becomes_a_terminal_failure(api):
    client, db, owner, _, _ = api
    client.post(URL, headers=owner, json={})
    job = db.scalar(select(CommonWordJob))
    job.attempts = 3
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert claim_job(db.get_bind()) is None
    db.expire_all()
    assert db.scalar(select(CommonWordJob)).failure_category == "attempts_exhausted"
    assert client.post(URL, headers=owner, json={}).json()["status"] == "failed"


def test_account_export_and_deletion_include_bank_and_jobs_and_stale_worker_cannot_restore(
    api, monkeypatch
):
    client, db, owner, other, _ = api
    generate(api, monkeypatch)
    owner_id = db.scalar(select(CommonWordQuestion.user_id))
    other_id = db.scalar(select(User.id).where(User.email == "other@example.com"))
    db.add(CommonWordJob(user_id=owner_id))
    db.add(CommonWordJob(user_id=other_id))
    db.commit()
    claimed = claim_job(db.get_bind())
    if claimed.user_id != owner_id:
        claimed = claim_job(db.get_bind())
    assert claimed.user_id == owner_id
    assert len(collect_user_data(db, owner_id)["common_word_questions"]) == 2
    assert collect_user_data(db, other_id)["common_word_questions"] == []
    db.rollback()
    assert client.delete("/api/v1/account", headers=owner).status_code == 204
    db.rollback()
    finish_job(db.get_bind(), claimed, [candidate("patient")])
    assert db.scalar(select(func.count()).select_from(CommonWordQuestion)) == 0
    assert db.get(CommonWordJob, other_id) is not None
    assert client.post(URL, headers=other, json={}).status_code == 202


@pytest.mark.parametrize(
    "body",
    [
        {"exclude_ids": ["bad-id"]},
        {"exclude_ids": [str(uuid.uuid4())] * 1001},
        {"user_id": str(uuid.uuid4())},
    ],
)
def test_request_validation_and_auth_do_not_queue_work(api, body):
    client, db, owner, _, _ = api
    assert client.post(URL, headers=owner, json=body).status_code == 422
    assert client.post(URL, json={}).status_code == 401
    assert db.scalar(select(func.count()).select_from(CommonWordJob)) == 0


def test_postgres_concurrent_requests_share_one_job_and_one_worker_claim(api):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from sqlalchemy.orm import Session

    from app.schemas.common_words import CommonBatchRequest
    from app.services.common_words import get_batch

    _client, db, _owner, _, _ = api
    engine = db.get_bind()
    if engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    owner_id = db.scalar(select(User.id).where(User.email == "owner@example.com"))
    db.rollback()
    start = Barrier(2)

    def request():
        with Session(engine) as connection:
            user = connection.get(User, owner_id)
            start.wait(timeout=10)
            return get_batch(connection, user, CommonBatchRequest()).status

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(request) for _ in range(2)]
        assert [future.result(timeout=15) for future in futures] == [
            "pending",
            "pending",
        ]
    assert db.scalar(select(func.count()).select_from(CommonWordJob)) == 1
    db.rollback()
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(claim_job, [engine, engine]))
    assert sum(claim is not None for claim in claims) == 1
