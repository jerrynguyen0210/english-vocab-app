"""API contracts for answers."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.models import ReviewAttempt, ReviewState, Word

from .helpers import create


def test_create_queue_submit_and_schedule(api):
    client, db, owner, other, _ = api
    response = create(client, owner)
    assert response.status_code == 201
    word_id = response.json()["id"]
    assert create(client, owner, " ＨELLO ").status_code == 409
    assert create(client, other).status_code == 201
    queue = client.get("/api/v1/reviews/next?limit=10", headers=owner)
    assert queue.status_code == 200
    assert queue.json() == [
        {
            "word_id": word_id,
            "english_explanation": "A greeting",
            "example_sentence": None,
        }
    ]
    assert "hello" not in queue.text.lower()
    assert queue.headers["cache-control"] == "no-store"
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": " HELLO ", "time_taken_ms": 400},
    )
    assert response.status_code == 200
    assert response.json()["result"] == "correct"
    assert response.json()["correct_word"] == "Hello"
    attempt = db.scalar(select(ReviewAttempt))
    assert attempt.normalised_answer == "hello" and attempt.time_taken_ms == 400
    state = db.get(ReviewState, uuid.UUID(word_id))
    assert state.correct_count == 1 and state.level == 1
    assert client.get("/api/v1/reviews/next", headers=owner).json() == []
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "Hello", "time_taken_ms": 1},
        ).status_code
        == 409
    )
    state.due_at = datetime.now(UTC) - timedelta(seconds=1)
    db.commit()
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": "", "time_taken_ms": 1},
    )
    assert response.json()["result"] == "incorrect"
    assert response.json()["correct_word"] == "Hello"
    assert state.incorrect_count == 1 and state.level == 0


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"typed_answer": "hello"},
        {"time_taken_ms": 1},
        {"typed_answer": None, "time_taken_ms": 1},
        {"typed_answer": 123, "time_taken_ms": 1},
        {"typed_answer": "x" * 201, "time_taken_ms": 1},
        {"typed_answer": "hello", "time_taken_ms": True},
        {"typed_answer": "hello", "time_taken_ms": "1"},
        {"typed_answer": "hello", "time_taken_ms": 1.5},
        {"typed_answer": "hello", "time_taken_ms": None},
        {"typed_answer": "hello", "time_taken_ms": 2147483648},
        {"typed_answer": "hello", "time_taken_ms": 1, "result": "correct"},
        {"typed_answer": "hello", "time_taken_ms": 1, "user_id": str(uuid.uuid4())},
    ],
)
def test_invalid_answer_requests_do_not_change_progress(api, body):
    client, db, owner, _, _ = api
    word_id = create(client, owner).json()["id"]
    state = db.get(ReviewState, uuid.UUID(word_id))
    due_at = state.due_at
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer", headers=owner, json=body
        ).status_code
        == 422
    )
    db.refresh(state)
    assert state.due_at == due_at and state.correct_count == state.incorrect_count == 0
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0


def test_queue_and_submission_isolate_accounts(api):
    client, db, owner, other, _ = api
    owner_id = create(client, owner, "OwnerWord").json()["id"]
    other_id = create(client, other, "OtherWord").json()["id"]
    assert client.get("/api/v1/reviews/next?limit=50", headers=owner).json() == [
        {
            "word_id": owner_id,
            "english_explanation": "A greeting",
            "example_sentence": None,
        }
    ]
    state = db.get(ReviewState, uuid.UUID(other_id))
    original_due = state.due_at
    response = client.post(
        f"/api/v1/reviews/{other_id}/answer",
        headers=owner,
        json={"typed_answer": "OtherWord", "time_taken_ms": 1},
    )
    assert response.status_code == 404 and "OtherWord" not in response.text
    db.refresh(state)
    assert state.due_at == original_due and state.correct_count == 0
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0
    assert client.get("/api/v1/reviews/next?limit=0", headers=owner).status_code == 422
    assert (
        client.get("/api/v1/reviews/next?limit=abc", headers=owner).status_code == 422
    )
    assert (
        client.post(
            "/api/v1/reviews/not-a-uuid/answer",
            headers=owner,
            json={"typed_answer": "x", "time_taken_ms": 1},
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("  TAKE a break  ", "correct"),
        ("take  a break", "incorrect"),
        ("take a break!", "incorrect"),
        ("take a brek", "incorrect"),
        ("ＴＡＫＥ a break", "incorrect"),
        ("", "incorrect"),
    ],
)
def test_d2_result_is_recorded(api, answer, expected):
    client, db, owner, _, _ = api
    word_id = create(client, owner, "Take a break").json()["id"]
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": answer, "time_taken_ms": 100},
    )
    assert response.status_code == 200
    assert response.json()["result"] == expected
    assert response.json()["correct_word"] == "Take a break"
    attempt = db.scalar(select(ReviewAttempt))
    assert attempt.typed_answer == answer
    assert attempt.result == expected
    assert attempt.time_taken_ms == 100


def test_reviews_continue_beyond_twenty_attempts_and_isolate_users(api):
    client, db, owner, other, _ = api
    # Seed more than the former daily cap; further reviews must remain available.
    word_id = create(client, owner, "First").json()["id"]
    word = db.get(Word, uuid.UUID(word_id))
    for _ in range(25):
        db.add(
            ReviewAttempt(
                word_id=word.id,
                user_id=word.user_id,
                typed_answer="First",
                result="correct",
                reviewed_at=datetime.now(UTC),
                time_taken_ms=1,
            )
        )
    db.commit()
    second = create(client, owner, "Second").json()["id"]
    preparation = client.get("/api/v1/reviews/preparation", headers=owner).json()
    assert preparation["count"] == 2
    items = client.get("/api/v1/reviews/session", headers=owner).json()
    assert len(items) == 2
    item = items[0]
    assert (
        client.post(
            f"/api/v1/reviews/{item['word_id']}/choices",
            headers=owner,
            json={
                "attempt_id": item["attempt_id"],
                "review_token": item["review_token"],
            },
        ).status_code
        == 200
    )
    assert len(client.get("/api/v1/reviews/next?limit=50", headers=owner).json()) == 2
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "wrong", "time_taken_ms": 10},
        ).status_code
        == 200
    )
    assert len(client.get("/api/v1/reviews/next", headers=owner).json()) == 1
    accepted = client.post(
        f"/api/v1/reviews/{second}/answer",
        headers=owner,
        json={"typed_answer": "Second", "time_taken_ms": 10},
    )
    assert accepted.status_code == 200
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 27
    assert db.get(ReviewState, uuid.UUID(second)).correct_count == 1
    other_word = create(client, other).json()["id"]
    assert len(client.get("/api/v1/reviews/next", headers=other).json()) == 1
    assert (
        client.post(
            f"/api/v1/reviews/{other_word}/answer",
            headers=other,
            json={"typed_answer": "Hello", "time_taken_ms": 10},
        ).status_code
        == 200
    )


def test_retry_after_lost_response_records_once(api):
    client, db, owner, other, _ = api
    word_id = create(client, owner).json()["id"]
    prompt = client.get("/api/v1/reviews/session", headers=owner).json()[0]
    body = {
        "attempt_id": prompt["attempt_id"],
        "typed_answer": "Hello",
        "time_taken_ms": 12,
    }
    first = client.post(f"/api/v1/reviews/{word_id}/answer", headers=owner, json=body)
    retry = client.post(f"/api/v1/reviews/{word_id}/answer", headers=owner, json=body)
    assert first.status_code == retry.status_code == 200
    assert first.json() == retry.json()
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 1
    assert db.get(ReviewState, uuid.UUID(word_id)).correct_count == 1
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={**body, "typed_answer": "changed"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer", headers=other, json=body
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "typed_answer,expected",
    [
        (" HELLO ", "correct"),
        ("helo", "incorrect"),
        ("hello!", "incorrect"),
        ("ＨＥＬＬＯ", "incorrect"),
    ],
)
def test_typing_session_hides_answer_until_d2_submission(api, typed_answer, expected):
    client, _, owner, _, _ = api
    saved = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "Hello",
            "english_explanation": "Hello is a greeting.",
            "example_sentence": "She said HELLO, then hello again.",
        },
    )
    assert saved.status_code == 201
    response = client.get("/api/v1/reviews/session?answer_mode=typing", headers=owner)
    assert response.status_code == 200
    item = response.json()[0]
    assert "choices" not in item and "word" not in item and "correct_word" not in item
    for key in ["prompt_sentence", "english_explanation", "example_sentence"]:
        assert "hello" not in item[key].casefold()
    assert response.headers["cache-control"] == "no-store"
    answer = client.post(
        f"/api/v1/reviews/{item['word_id']}/answer",
        headers=owner,
        json={
            "attempt_id": item["attempt_id"],
            "review_token": item["review_token"],
            "typed_answer": typed_answer,
            "time_taken_ms": 1,
        },
    )
    assert answer.status_code == 200
    assert answer.json()["result"] == expected
    assert answer.json()["correct_word"] == "Hello"


@pytest.mark.parametrize("correct", [True, False])
def test_choice_answer_persists_result_and_sm2_schedule(api, correct):
    client, db, owner, _, _ = api
    word_id = create(client, owner).json()["id"]
    item = client.get(
        "/api/v1/reviews/session?answer_mode=choice", headers=owner
    ).json()[0]
    selected = (
        "Hello"
        if correct
        else next(choice for choice in item["choices"] if choice != "Hello")
    )
    response = client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={
            "attempt_id": item["attempt_id"],
            "review_token": item["review_token"],
            "typed_answer": selected,
            "time_taken_ms": 123,
        },
    )
    assert response.status_code == 200
    expected = "correct" if correct else "incorrect"
    assert response.json()["result"] == expected
    assert response.json()["correct_word"] == "Hello"
    db.expire_all()
    attempt = db.scalar(select(ReviewAttempt))
    assert attempt.result == expected
    assert attempt.typed_answer == selected
    assert attempt.time_taken_ms == 123
    state = db.get(ReviewState, uuid.UUID(word_id))
    assert (state.correct_count, state.incorrect_count) == (
        (1, 0) if correct else (0, 1)
    )
    assert state.repetitions == (1 if correct else 0)
    assert state.interval_days == (1 if correct else 0)
    assert state.ease_factor == pytest.approx(2.5 if correct else 1.96)
    from app.core.time import as_utc

    assert as_utc(state.due_at) - as_utc(attempt.reviewed_at) == (
        timedelta(days=1) if correct else timedelta(minutes=10)
    )
