import uuid
from datetime import UTC, datetime, timedelta

from app.models import ReviewState
from app.services.review_ticket import issue_ticket, valid_ticket


def test_session_ticket_is_scoped_expires_and_invalidates_after_another_review():
    now = datetime(2026, 11, 11, tzinfo=UTC)
    user, attempt = uuid.uuid4(), uuid.uuid4()
    state = ReviewState(word_id=uuid.uuid4(), due_at=now)
    token = issue_ticket(user, state, attempt, now)
    assert valid_ticket(token, user, state, attempt, now)
    assert not valid_ticket(token, uuid.uuid4(), state, attempt, now)
    assert not valid_ticket(token, user, state, uuid.uuid4(), now)
    assert not valid_ticket(
        token, user, state, attempt, now + timedelta(days=1, seconds=1)
    )
    state.last_reviewed_at = now
    assert not valid_ticket(token, user, state, attempt, now)
    assert not valid_ticket("broken", user, state, attempt, now)
