"""Run with python -m app.prompt_worker; no LLM work runs in HTTP requests."""

import logging
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_engine
from app.llm.ollama_review import ReviewError, generate_review
from app.models import PromptJob, User, Word

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedJob:
    word_id: uuid.UUID
    user_id: uuid.UUID
    token: uuid.UUID
    word: str
    meaning: str
    attempts: int


def claim_job(engine: Engine) -> ClaimedJob | None:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        job = db.scalar(
            select(PromptJob)
            .where(PromptJob.available_at <= now)
            .order_by(PromptJob.available_at, PromptJob.word_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        token = uuid.uuid4()
        # The conditional update also prevents double claims without row locking.
        claimed = db.execute(
            update(PromptJob)
            .where(PromptJob.word_id == job.word_id, PromptJob.available_at <= now)
            .values(
                lease_token=token,
                attempts=PromptJob.attempts + 1,
                available_at=now
                + timedelta(seconds=get_settings().ollama_timeout_seconds + 60),
            )
            .returning(PromptJob.attempts)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if claimed is None:
            return None
        word = db.get(Word, job.word_id)
        assert word is not None
        return ClaimedJob(
            word.id, word.user_id, token, word.word, word.english_explanation, claimed
        )


def finish_job(engine: Engine, claimed: ClaimedJob, prompt: str | None) -> None:
    with Session(engine) as db, db.begin():
        # Match account erasure's lock ordering and never resurrect deleted data.
        owner = db.scalar(
            select(User.id).where(User.id == claimed.user_id).with_for_update()
        )
        if owner is None:
            return
        job = db.scalar(
            select(PromptJob)
            .where(
                PromptJob.word_id == claimed.word_id,
                PromptJob.lease_token == claimed.token,
            )
            .with_for_update()
        )
        if job is None:
            return  # Deleted or reclaimed after this worker's lease expired.
        if prompt is None:
            job.lease_token = None
            job.available_at = datetime.now(UTC) + timedelta(
                seconds=min(3600, 5 * 2 ** min(claimed.attempts, 10))
            )
        else:
            db.execute(
                update(Word)
                .where(Word.id == claimed.word_id)
                .values(review_prompt=prompt)
            )
            db.delete(job)


def process_one(engine: Engine) -> bool:
    claimed = claim_job(engine)
    if claimed is None:
        return False
    settings = get_settings()
    try:
        result = generate_review(
            claimed.word,
            claimed.meaning,
            model=settings.ollama_model,
            base_url=settings.ollama_url,
            timeout=settings.ollama_timeout_seconds,
        )
    except (ReviewError, ValueError):
        # Avoid logging user vocabulary or provider error bodies.
        logger.warning(
            "Prompt generation failed; scheduling retry (attempt %s)", claimed.attempts
        )
        finish_job(engine, claimed, None)
    else:
        finish_job(engine, claimed, result["prompt_sentence"])
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    engine = get_engine()
    try:
        while True:
            try:
                if not process_one(engine):
                    time.sleep(1)
            except SQLAlchemyError:
                # Crashed/incomplete jobs become claimable when their lease expires.
                logger.error(
                    "Prompt worker encountered an error; retrying after 5 seconds"
                )
                time.sleep(5)
    except KeyboardInterrupt:
        pass
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
