"""Claim Common bank refills, call the LLM outside transactions, then filter."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import Engine, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.text import normalise_word
from app.llm.openrouter_common import generate_common_words
from app.llm.openrouter_review import ReviewError
from app.models import CommonWordJob, CommonWordQuestion, User, Word
from app.schemas.common_words import GeneratedCommonWord

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class ClaimedJob:
    user_id: uuid.UUID
    token: uuid.UUID
    attempts: int
    excluded_words: list[str]
    learned_words: list[str]


def claim_job(engine: Engine) -> ClaimedJob | None:
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        db.execute(
            update(CommonWordJob)
            .where(
                CommonWordJob.failed_at.is_(None),
                CommonWordJob.available_at <= now,
                CommonWordJob.attempts >= MAX_ATTEMPTS,
            )
            .values(
                failed_at=now, failure_category="attempts_exhausted", lease_token=None
            )
        )
        job = db.scalar(
            select(CommonWordJob)
            .where(
                CommonWordJob.failed_at.is_(None),
                CommonWordJob.available_at <= now,
                CommonWordJob.attempts < MAX_ATTEMPTS,
            )
            .order_by(CommonWordJob.available_at, CommonWordJob.user_id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        token = uuid.uuid4()
        attempts = db.execute(
            update(CommonWordJob)
            .where(
                CommonWordJob.user_id == job.user_id,
                CommonWordJob.available_at <= now,
                CommonWordJob.failed_at.is_(None),
                CommonWordJob.attempts < MAX_ATTEMPTS,
            )
            .values(
                lease_token=token,
                attempts=CommonWordJob.attempts + 1,
                available_at=now
                + timedelta(seconds=get_settings().common_words_timeout_seconds + 60),
            )
            .returning(CommonWordJob.attempts)
            .execution_options(synchronize_session=False)
        ).scalar_one_or_none()
        if attempts is None:
            return None
        # Include all learned and saved words, plus recent generated questions.
        # Only generated, unlearned history is capped; learned memory is durable.
        learned = list(
            db.scalars(
                select(CommonWordQuestion.normalised_word)
                .where(
                    CommonWordQuestion.user_id == job.user_id,
                    CommonWordQuestion.learned_at.is_not(None),
                )
                .order_by(CommonWordQuestion.normalised_word)
            )
        )
        excluded = set(
            db.scalars(select(Word.normalised_word).where(Word.user_id == job.user_id))
        )
        excluded.update(
            db.scalars(
                select(CommonWordQuestion.normalised_word)
                .where(
                    CommonWordQuestion.user_id == job.user_id,
                    CommonWordQuestion.learned_at.is_(None),
                )
                .order_by(CommonWordQuestion.created_at.desc(), CommonWordQuestion.id)
                .limit(500)
            )
        )
        return ClaimedJob(job.user_id, token, attempts, sorted(excluded), learned)


def finish_job(
    engine: Engine,
    claimed: ClaimedJob,
    candidates: list[GeneratedCommonWord] | None,
    failure_category: str = "generation_error",
) -> None:
    with Session(engine) as db, db.begin():
        owner = db.scalar(
            select(User).where(User.id == claimed.user_id).with_for_update()
        )
        if (
            owner is None
            or owner.deleted_at is not None
            or owner.disabled_at is not None
        ):
            return
        job = db.scalar(
            select(CommonWordJob)
            .where(
                CommonWordJob.user_id == claimed.user_id,
                CommonWordJob.lease_token == claimed.token,
            )
            .with_for_update()
        )
        if job is None:
            return
        inserted = 0
        if candidates is not None:
            # Fetch after generation, under the same account lock used by Save word.
            # This covers saves on another device while the model was running.
            excluded = set(
                db.scalars(
                    select(Word.normalised_word).where(Word.user_id == claimed.user_id)
                )
            )
            excluded.update(
                db.scalars(
                    select(CommonWordQuestion.normalised_word).where(
                        CommonWordQuestion.user_id == claimed.user_id,
                    )
                )
            )
            for candidate in candidates:
                normalised = normalise_word(candidate.word)
                if normalised in excluded:
                    continue
                db.add(
                    CommonWordQuestion(
                        user_id=claimed.user_id,
                        word=candidate.word,
                        ipa=candidate.ipa,
                        normalised_word=normalised,
                        part_of_speech=candidate.part_of_speech,
                        explanation=candidate.explanation,
                        example=candidate.example,
                        choices=candidate.choices,
                        correct_index=candidate.correct_index,
                    )
                )
                excluded.add(normalised)
                inserted += 1
        if inserted:
            db.delete(job)
        else:
            job.lease_token = None
            job.failure_category = (
                "no_new_words" if candidates is not None else failure_category
            )
            if claimed.attempts >= MAX_ATTEMPTS:
                job.failed_at = datetime.now(UTC)
            else:
                job.available_at = datetime.now(UTC) + timedelta(
                    seconds=5 * 2**claimed.attempts
                )


def process_one(engine: Engine) -> bool:
    claimed = claim_job(engine)
    if claimed is None:
        return False
    settings = get_settings()
    try:
        candidates = generate_common_words(
            claimed.excluded_words,
            learned_words=claimed.learned_words,
            model=settings.openrouter_model,
            api_key=settings.openrouter_api_key.get_secret_value(),
            base_url=settings.openrouter_url,
            timeout=settings.common_words_timeout_seconds,
        )
    except (ReviewError, ValueError) as error:
        logger.warning("Common word generation failed (attempt %s)", claimed.attempts)
        finish_job(
            engine,
            claimed,
            None,
            error.category if isinstance(error, ReviewError) else "invalid_response",
        )
    else:
        finish_job(engine, claimed, candidates)
    return True
