"""Signed, expiring session authorization, bound to an unchanged review state."""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime

from app.core.config import get_settings
from app.models import ReviewState


def _signature(payload: str) -> str:
    return hmac.new(
        get_settings().secret_key.get_secret_value().encode(),
        ("review-session:" + payload).encode(),
        hashlib.sha256,
    ).hexdigest()


def issue_ticket(
    user_id: uuid.UUID, state: ReviewState, attempt_id: uuid.UUID, now: datetime
) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps(
            [
                str(user_id),
                str(state.word_id),
                str(attempt_id),
                state.last_reviewed_at.isoformat() if state.last_reviewed_at else None,
                state.due_at.isoformat(),
                int(now.timestamp()) + 86400,
            ]
        ).encode()
    ).decode()
    return payload + "." + _signature(payload)


def valid_ticket(
    token: str,
    user_id: uuid.UUID,
    state: ReviewState,
    attempt_id: uuid.UUID | None,
    now: datetime,
) -> bool:
    try:
        payload, signature = token.rsplit(".", 1)
        if not hmac.compare_digest(signature, _signature(payload)):
            return False
        data = json.loads(base64.urlsafe_b64decode(payload))
        return bool(
            data[:5]
            == [
                str(user_id),
                str(state.word_id),
                str(attempt_id),
                state.last_reviewed_at.isoformat() if state.last_reviewed_at else None,
                state.due_at.isoformat(),
            ]
            and data[5] >= now.timestamp()
        )
    except (ValueError, TypeError, IndexError):
        return False
