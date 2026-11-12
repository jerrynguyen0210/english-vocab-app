"""API contracts for prompt worker."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import event, func, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import ReviewState, User, Word

from .helpers import create


def test_failed_jobs_stop_retrying_and_can_be_monitored_and_reset(api, monkeypatch):
    from app.llm.openrouter_review import ReviewError
    from app.models import PromptJob
    from app.services.prompt_jobs.management import queue_status, retry_failed_job
    from app.services.prompt_jobs.worker import process_one

    client, db, owner, _, _ = api
    settings = get_settings()
    monkeypatch.setattr(settings, "prompt_job_max_attempts", 2)
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(1)
        raise ReviewError(
            "Private provider response must not be stored", "provider_connection"
        )

    monkeypatch.setattr("app.services.prompt_jobs.worker.generate_review", unavailable)
    word_id = uuid.UUID(create(client, owner).json()["id"])
    db.rollback()
    engine = db.get_bind()
    assert process_one(engine)
    db.expire_all()
    job = db.get(PromptJob, word_id)
    assert job.failed_at is None
    assert job.failure_category == "provider_connection"
    assert queue_status(db)["waiting_retry"] == 1
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert process_one(engine)
    db.expire_all()
    job = db.get(PromptJob, word_id)
    assert job.failed_at is not None
    assert job.attempts == 2
    status = queue_status(db)
    assert status["failed"] == 1
    assert status["failures"][0]["word_id"] == word_id
    assert "Private provider" not in str(status)
    fallback = db.get(Word, word_id).review_prompt
    db.rollback()
    assert not process_one(engine)
    assert len(calls) == 2
    retry_failed_job(db, word_id)
    with pytest.raises(LookupError):
        retry_failed_job(db, word_id)  # Never reset pending or in-flight work.
    db.rollback()
    assert queue_status(db)["pending"] == 1
    db.rollback()
    monkeypatch.setattr(
        "app.services.prompt_jobs.worker.generate_review",
        lambda *args, **kwargs: {"prompt_sentence": "She said _____."},
    )
    assert process_one(engine)
    db.expire_all()
    assert db.get(PromptJob, word_id) is None
    assert db.get(Word, word_id).review_prompt != fallback


def test_crashed_final_attempt_becomes_failed_after_lease_expires(api, monkeypatch):
    from app.models import PromptJob
    from app.services.prompt_jobs.management import queue_status
    from app.services.prompt_jobs.worker import claim_job, finish_job

    client, db, owner, _, _ = api
    monkeypatch.setattr(get_settings(), "prompt_job_max_attempts", 1)
    word_id = uuid.UUID(create(client, owner).json()["id"])
    db.rollback()
    engine = db.get_bind()
    claimed = claim_job(engine)
    assert claimed is not None
    assert queue_status(db)["in_flight"] == 1
    job = db.get(PromptJob, word_id)
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert claim_job(engine) is None
    db.expire_all()
    job = db.get(PromptJob, word_id)
    assert job.failed_at is not None
    assert job.failure_category == "attempts_exhausted"
    db.rollback()
    finish_job(engine, claimed, "Stale _____ result.")
    db.expire_all()
    assert db.get(PromptJob, word_id) is not None
    assert db.get(Word, word_id).review_prompt != "Stale _____ result."


def test_generated_prompt_is_persisted_and_reused_without_openrouter(api, monkeypatch):
    from unittest.mock import Mock

    client, db, owner, _, _ = api
    generator = Mock(
        return_value={
            "prompt_sentence": "She was _____ to leave her friends.",
            "answer": "reluctant",
        }
    )
    monkeypatch.setattr("app.services.prompt_jobs.worker.generate_review", generator)
    response = create(client, owner, "reluctant")
    assert response.status_code == 201
    generator.assert_not_called()
    from app.services.prompt_jobs.worker import process_one

    assert process_one(db.get_bind())
    word_id = uuid.UUID(response.json()["id"])
    db.expire_all()
    stored = db.get(Word, word_id)
    assert stored.review_prompt == "She was _____ to leave her friends."
    generator.assert_called_once_with(
        "reluctant",
        "A greeting",
        model=get_settings().openrouter_model,
        api_key=get_settings().openrouter_api_key.get_secret_value(),
        base_url=get_settings().openrouter_url,
        timeout=get_settings().openrouter_timeout_seconds,
    )
    generator.side_effect = AssertionError("Review reads must never call OpenRouter")
    assert create(client, owner, "RELUCTANT").status_code == 409
    first = client.get("/api/v1/reviews/session", headers=owner).json()[0]
    second = client.get("/api/v1/reviews/session", headers=owner).json()[0]
    choices = client.post(
        f"/api/v1/reviews/{word_id}/choices",
        headers=owner,
        json={"attempt_id": first["attempt_id"], "review_token": first["review_token"]},
    )
    assert choices.status_code == 200
    for item in (first, second, choices.json()):
        assert item["prompt_sentence"] == stored.review_prompt
        assert "answer" not in item and "correct_word" not in item
    assert generator.call_count == 1


def test_generation_failure_keeps_word_and_retries_in_worker(api, monkeypatch):
    from unittest.mock import Mock

    from app.llm.openrouter_review import ReviewError
    from app.models import PromptJob
    from app.services.prompt_jobs.worker import process_one

    client, db, owner, _, _ = api
    generator = Mock(side_effect=ReviewError("Unavailable"))
    monkeypatch.setattr("app.services.prompt_jobs.worker.generate_review", generator)
    response = create(client, owner)
    assert response.status_code == 201
    generator.assert_not_called()
    word_id = uuid.UUID(response.json()["id"])
    assert db.scalar(select(func.count()).select_from(Word)) == 1
    assert db.scalar(select(func.count()).select_from(ReviewState)) == 1
    db.rollback()
    assert process_one(db.get_bind())
    db.expire_all()
    job = db.get(PromptJob, word_id)
    assert job.attempts == 1
    assert job.available_at > datetime.now(UTC)
    assert "A greeting" in db.get(Word, word_id).review_prompt
    assert create(client, owner).status_code == 409
    assert db.scalar(select(func.count()).select_from(PromptJob)) == 1
    generator.side_effect = None
    generator.return_value = {
        "prompt_sentence": "She said _____ to greet me.",
        "answer": "Hello",
    }
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    assert process_one(db.get_bind())
    db.expire_all()
    assert db.get(PromptJob, word_id) is None
    assert db.get(Word, word_id).review_prompt == "She said _____ to greet me."


def test_prompt_worker_recovers_expired_lease_and_ignores_stale_result(api):
    from app.models import PromptJob
    from app.services.prompt_jobs.worker import claim_job, finish_job

    client, db, owner, _, _ = api
    word_id = uuid.UUID(create(client, owner).json()["id"])
    db.rollback()
    engine = db.get_bind()
    first = claim_job(engine)
    assert first.word_id == word_id
    assert claim_job(engine) is None
    job = db.get(PromptJob, word_id)
    job.available_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    second = claim_job(engine)
    assert second.attempts == 2
    assert second.token != first.token
    finish_job(engine, first, "Stale _____ prompt.")
    db.expire_all()
    assert db.get(Word, word_id).review_prompt != "Stale _____ prompt."
    assert db.get(PromptJob, word_id) is not None
    db.rollback()
    finish_job(engine, second, "Current _____ prompt.")
    db.expire_all()
    assert db.get(Word, word_id).review_prompt == "Current _____ prompt."
    assert db.get(PromptJob, word_id) is None


def test_account_erasure_removes_queued_and_inflight_prompts(api):
    from app.models import PromptJob
    from app.services.accounts import delete_account
    from app.services.prompt_jobs.worker import claim_job, finish_job

    client, db, owner, _, _ = api
    word_id = uuid.UUID(create(client, owner).json()["id"])
    assert create(client, owner, "another").status_code == 201
    db.rollback()
    claimed = claim_job(db.get_bind())
    user = db.get(User, db.get(Word, word_id).user_id)
    delete_account(db, user)
    finish_job(db.get_bind(), claimed, "Discarded _____ prompt.")
    assert db.scalar(select(func.count()).select_from(PromptJob)) == 0
    assert db.scalar(select(func.count()).select_from(Word)) == 0


def test_enqueue_failure_rolls_back_word_and_review_state(api):
    from app.models import PromptJob
    from app.schemas.words import CreateWord
    from app.services.words import create_word

    _, db, _, _, _ = api
    user = db.scalar(select(User).where(User.email == "owner@example.com"))

    def reject_job(mapper, connection, target):
        raise RuntimeError("Simulated queue insertion failure")

    event.listen(PromptJob, "before_insert", reject_job)
    try:
        with pytest.raises(RuntimeError, match="queue insertion failure"):
            create_word(
                CreateWord(word="Hello", english_explanation="Greeting"), db, user
            )
        db.rollback()
    finally:
        event.remove(PromptJob, "before_insert", reject_job)
    assert db.scalar(select(func.count()).select_from(Word)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewState)) == 0
    assert db.scalar(select(func.count()).select_from(PromptJob)) == 0


def test_prompt_worker_skips_jobs_locked_by_another_worker(api):
    from app.models import PromptJob
    from app.services.prompt_jobs.worker import claim_job

    client, db, owner, _, _ = api
    engine = db.get_bind()
    if engine.dialect.name != "postgresql":
        pytest.skip("Row-lock concurrency requires PostgreSQL")
    first_id = uuid.UUID(create(client, owner).json()["id"])
    second_id = uuid.UUID(create(client, owner, "another").json()["id"])
    db.rollback()
    with Session(engine) as locked, locked.begin():
        locked.execute(text("SET LOCAL statement_timeout = '3s'"))
        locked.scalar(
            select(PromptJob).where(PromptJob.word_id == first_id).with_for_update()
        )
        claimed = claim_job(engine)
        assert claimed.word_id == second_id
    claimed = claim_job(engine)
    assert claimed.word_id == first_id
    assert claim_job(engine) is None
