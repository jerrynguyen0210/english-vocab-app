"""Account locking and atomic account erasure."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import (
    AuthSession,
    CommonPracticeQuestion,
    ReviewAttempt,
    ReviewState,
    User,
    UserCommonWordProgress,
    Word,
)
from app.schemas.account import AccountUpdate
from app.services.errors import AccountUnavailable


def lock_account(db: Session, user: User) -> None:
    lock_account_by_id(db, user.id)


def lock_account_by_id(db: Session, user_id: UUID) -> None:
    # Use the stable ID after external I/O: the ORM account may have been expired
    # and deleted in another session while generation was running.
    active = db.scalar(
        select(User.id)
        .where(
            User.id == user_id, User.deleted_at.is_(None), User.disabled_at.is_(None)
        )
        .with_for_update()
    )
    if active is None:
        raise AccountUnavailable("Account unavailable")


def update_account(db: Session, user: User, body: AccountUpdate) -> User:
    lock_account(db, user)
    user.timezone = body.timezone
    db.commit()
    return user


def delete_account(db: Session, user: User) -> None:
    lock_account(db, user)
    # The trigger permits erasure only after this marker, in the same transaction.
    user.deleted_at = datetime.now(UTC)
    db.flush()
    word_ids = select(Word.id).where(Word.user_id == user.id)
    db.execute(
        delete(CommonPracticeQuestion).where(CommonPracticeQuestion.user_id == user.id)
    )
    db.execute(
        delete(UserCommonWordProgress).where(UserCommonWordProgress.user_id == user.id)
    )
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(ReviewAttempt).where(ReviewAttempt.user_id == user.id))
    db.execute(delete(ReviewState).where(ReviewState.word_id.in_(word_ids)))
    db.execute(delete(Word).where(Word.user_id == user.id))
    db.delete(user)
    db.commit()
