"""Account locking and atomic account erasure."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuthSession, ReviewAttempt, ReviewState, User, Word
from app.services.errors import AccountUnavailable


def lock_account(db: Session, user: User) -> None:
    # Serialize mutations with account erasure and recheck after acquiring the lock.
    active = db.scalar(
        select(User.id)
        .where(
            User.id == user.id, User.deleted_at.is_(None), User.disabled_at.is_(None)
        )
        .with_for_update()
    )
    if active is None:
        raise AccountUnavailable("Account unavailable")


def delete_account(db: Session, user: User) -> None:
    lock_account(db, user)
    # The trigger permits erasure only after this marker, in the same transaction.
    user.deleted_at = datetime.now(UTC)
    db.flush()
    word_ids = select(Word.id).where(Word.user_id == user.id)
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.execute(delete(ReviewAttempt).where(ReviewAttempt.user_id == user.id))
    db.execute(delete(ReviewState).where(ReviewState.word_id.in_(word_ids)))
    db.execute(delete(Word).where(Word.user_id == user.id))
    db.delete(user)
    db.commit()
