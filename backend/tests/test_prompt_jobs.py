"""Operator commands report safe queue metadata and retry only failed work."""

import json
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app import prompt_jobs
from app.core.database import Base
from app.models import PromptJob, User, Word


def test_operator_status_and_retry_commands(tmp_path, monkeypatch, capsys):
    engine = create_engine(f"sqlite:///{tmp_path}/queue.db")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="operator-test@example.test", password_hash="placeholder")
        db.add(user)
        db.flush()
        word = Word(
            user_id=user.id,
            word="private vocabulary",
            english_explanation="Private meaning",
        )
        db.add(word)
        db.flush()
        word_id = word.id
        db.add(
            PromptJob(
                word_id=word_id,
                attempts=5,
                failed_at=datetime.now(UTC),
                failure_category="provider_connection",
            )
        )
        db.commit()
    monkeypatch.setattr(prompt_jobs, "get_engine", lambda: engine)
    monkeypatch.setattr("sys.argv", ["prompt_jobs", "status"])
    prompt_jobs.main()
    output = capsys.readouterr().out
    status = json.loads(output)
    assert status["failed"] == 1 and status["pending"] == 0
    assert status["failures"][0]["word_id"] == str(word_id)
    assert "private vocabulary" not in output and "Private meaning" not in output

    monkeypatch.setattr("sys.argv", ["prompt_jobs", "retry", "--word-id", str(word_id)])
    prompt_jobs.main()
    capsys.readouterr()
    with Session(engine) as db:
        job = db.get(PromptJob, word_id)
        assert job.attempts == 0 and job.failed_at is None
        assert job.lease_token is None and job.failure_category is None
    # An existing pending job, like a missing identifier, cannot be reset.
    for target in [word_id, uuid.uuid4()]:
        monkeypatch.setattr(
            "sys.argv", ["prompt_jobs", "retry", "--word-id", str(target)]
        )
        with pytest.raises(SystemExit) as error:
            prompt_jobs.main()
        assert error.value.code == 1
    engine.dispose()
