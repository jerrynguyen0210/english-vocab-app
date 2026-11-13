"""API contracts for sessions."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from app.core.text import normalise_word
from app.models import ReviewAttempt, ReviewState, User, Word

from .helpers import create


def test_choice_preparation_bounds_profiles_even_for_large_banks(api, monkeypatch):
    from app.services.reviews import service

    client, db, owner, _, _ = api
    user_id = uuid.UUID(client.get("/api/v1/auth/me", headers=owner).json()["id"])
    words = [
        Word(
            id=uuid.UUID(int=index + 1),
            user_id=user_id,
            word=f"candidate{index}",
            english_explanation="A candidate",
        )
        for index in range(service.CHOICE_CANDIDATE_LIMIT + 100)
    ]
    targets = [
        Word(
            id=uuid.UUID(int=1000 + index),
            user_id=user_id,
            word=f"target{index}",
            english_explanation="A target",
        )
        for index in range(50)
    ]
    db.add_all([*words, *targets])
    db.flush()
    db.add_all([ReviewState(word_id=word.id) for word in targets])
    db.commit()
    profiled = []

    def parts(word):
        profiled.append(word)
        return frozenset()

    monkeypatch.setattr(service, "review_parts", parts)
    monkeypatch.setattr("app.services.reviews.choices.review_family", lambda word: ())
    response = client.get("/api/v1/reviews/session?answer_mode=choice", headers=owner)
    assert response.status_code == 200
    assert len(response.json()) == 50
    assert len(profiled) == service.CHOICE_CANDIDATE_LIMIT + 50
    assert {word.word for word in targets} <= set(profiled)
    for item in response.json():
        assert len(set(item["choices"])) == 4
    item = response.json()[0]
    profiled.clear()
    switched = client.post(
        f"/api/v1/reviews/{item['word_id']}/choices",
        headers=owner,
        json={"attempt_id": item["attempt_id"], "review_token": item["review_token"]},
    )
    assert switched.status_code == 200
    assert len(profiled) == service.CHOICE_CANDIDATE_LIMIT + 1


def test_review_hints_mask_answer_before_serialization(api):
    client, _, owner, _, _ = api
    created = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "resilience",
            "english_explanation": "Resilience means recovering after setbacks.",
            "example_sentence": "Her RESILIENCE showed; resilience matters.",
        },
    )
    assert created.status_code == 201
    response = client.get("/api/v1/reviews/next", headers=owner)
    assert response.status_code == 200
    assert response.json() == [
        {
            "word_id": created.json()["id"],
            "english_explanation": "_____ means recovering after setbacks.",
            "example_sentence": "Her _____ showed; _____ matters.",
        }
    ]
    assert "resilience" not in response.text.lower()


def test_session_snapshot_excludes_later_additions(api):
    client, _, owner, _, _ = api
    assert client.get("/api/v1/reviews/session", headers=owner).json() == []
    first = create(client, owner).json()["id"]
    snapshot = client.get("/api/v1/reviews/session", headers=owner).json()
    second = create(client, owner, "Later").json()["id"]
    assert [p["word_id"] for p in snapshot] == [first]
    assert {
        p["word_id"]
        for p in client.get("/api/v1/reviews/session", headers=owner).json()
    } == {first, second}
    assert client.get("/api/v1/reviews/session").status_code == 401


def test_preparation_windows_and_overdue_are_user_local(api, monkeypatch):
    from app.core.time import local_day_bounds
    from app.services.reviews import service as reviews_service

    client, db, owner, other, _ = api
    now = datetime(2026, 10, 5, 2, tzinfo=UTC)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now

    monkeypatch.setattr(reviews_service, "datetime", Clock)
    user = db.scalar(select(User).where(User.email == "owner@example.com"))
    user.timezone = "Australia/Sydney"
    start, end = local_day_bounds(now, user.timezone)
    dates = [
        datetime(2026, 10, 3, 13, 59, tzinfo=UTC),
        datetime(2026, 10, 3, 14, tzinfo=UTC),
        datetime(2026, 10, 4, 12, 59, tzinfo=UTC),
        start,
        now - timedelta(days=7),
        now - timedelta(days=7, seconds=1),
        now - timedelta(days=30),
        now - timedelta(days=30, seconds=1),
    ]
    for index, saved_at in enumerate(dates):
        word = Word(
            user_id=user.id,
            word=f"word{index}",
            english_explanation="Meaning",
            created_at=saved_at,
        )
        db.add(word)
        db.flush()
        db.add(
            ReviewState(
                word_id=word.id,
                due_at=[
                    start - timedelta(seconds=1),
                    start,
                    end - timedelta(seconds=1),
                    end,
                ][index % 4],
            )
        )
    db.commit()
    for params, expected in [
        ({"source": "time", "period": "Yesterday"}, 2),
        ({"source": "time", "period": "Weekly"}, 5),
        ({"source": "time", "period": "Monthly"}, 7),
        ({"source": "recall", "include_overdue": True}, 6),
        ({"source": "recall", "include_overdue": False}, 4),
    ]:
        response = client.get(
            "/api/v1/reviews/preparation", params=params, headers=owner
        )
        assert response.status_code == 200, response.text
        assert response.json() == {
            "count": expected,
            "matching_count": expected,
            "saved_count": 8,
            "due_count": 6,
            "daily_remaining": 50,
        }
        assert (
            len(
                client.get(
                    "/api/v1/reviews/session", params=params, headers=owner
                ).json()
            )
            == expected
        )
        assert (
            client.get(
                "/api/v1/reviews/preparation", params=params, headers=other
            ).json()["count"]
            == 0
        )
    assert (
        client.get(
            "/api/v1/reviews/preparation?source=time&period=Tomorrow", headers=owner
        ).status_code
        == 422
    )


def test_time_session_authorizes_not_due_answers(api):
    client, db, owner, other, _ = api
    for word in ["hello", "concise"]:
        response = client.post(
            "/api/v1/words",
            headers=owner,
            json={"word": word, "english_explanation": f"{word} means something"},
        )
        assert response.status_code == 201
        db.get(ReviewState, uuid.UUID(response.json()["id"])).due_at = datetime.now(
            UTC
        ) + timedelta(days=20)
    db.commit()
    query = "?source=time&period=Weekly&answer_mode=choice"
    response = client.get("/api/v1/reviews/preparation" + query, headers=owner)
    assert response.json() == {
        "count": 2,
        "matching_count": 2,
        "saved_count": 2,
        "due_count": 0,
        "daily_remaining": 50,
    }
    assert response.headers["cache-control"] == "no-store"
    items = client.get("/api/v1/reviews/session" + query, headers=owner).json()
    assert len(items) == 2
    first = items[0]
    word = db.get(Word, uuid.UUID(first["word_id"]))
    assert word.word in first["choices"]
    assert word.word not in first["english_explanation"]
    body = {
        "attempt_id": first["attempt_id"],
        "review_token": first["review_token"],
        "typed_answer": word.word,
        "time_taken_ms": 123,
    }
    path = f"/api/v1/reviews/{first['word_id']}/answer"
    assert client.post(path, headers=other, json=body).status_code == 404
    assert (
        client.post(
            path,
            headers=owner,
            json={**body, "review_token": body["review_token"] + "x"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            path,
            headers=owner,
            json={key: value for key, value in body.items() if key != "review_token"},
        ).status_code
        == 409
    )
    result = client.post(path, headers=owner, json=body)
    assert result.status_code == 200, result.text
    assert client.post(path, headers=owner, json=body).status_code == 200
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 1
    assert (
        client.post(
            path, headers=owner, json={**body, "attempt_id": str(uuid.uuid4())}
        ).status_code
        == 409
    )
    assert client.get("/api/v1/reviews/preparation").status_code == 401
    assert client.delete("/api/v1/account", headers=owner).status_code == 204


def test_preparation_unlimited_reviews_and_four_options_for_small_bank(api):
    client, _, owner, _, _ = api
    create(client, owner)
    item = client.get(
        "/api/v1/reviews/session?source=recall&answer_mode=choice", headers=owner
    ).json()[0]
    assert len(item["choices"]) == 4
    assert len({normalise_word(option) for option in item["choices"]}) == 4
    assert sum(normalise_word(option) == "hello" for option in item["choices"]) == 1
    create(client, owner, "bye")
    assert client.get(
        "/api/v1/reviews/preparation?source=recall", headers=owner
    ).json() == {
        "count": 2,
        "matching_count": 2,
        "saved_count": 2,
        "due_count": 2,
        "daily_remaining": 50,
    }
    result = client.post(
        f"/api/v1/reviews/{item['word_id']}/answer",
        headers=owner,
        json={
            "attempt_id": item["attempt_id"],
            "review_token": item["review_token"],
            "typed_answer": "Hello",
            "time_taken_ms": 1,
        },
    )
    assert result.status_code == 200
    assert (
        client.get("/api/v1/reviews/preparation?source=time", headers=owner).json()[
            "count"
        ]
        == 2
    )
    assert (
        len(client.get("/api/v1/reviews/session?source=time", headers=owner).json())
        == 2
    )


@pytest.mark.parametrize(
    ("word", "example", "explanation", "expected"),
    [
        (
            "resilience",
            "Her RESILIENCE helped; resilience matters.",
            "Resilience is the ability to recover.",
            "Her _____ helped; _____ matters.",
        ),
        (
            "straße",
            "Try ＳＴＲＡＳＳＥ and Straße.",
            "A road.",
            "Try _____ and _____. ",
        ),
        ("take a break", "We take\na break at noon.", "To pause.", "We _____ at noon."),
        ("hello", None, "A greeting.", "“_____” means: A greeting."),
        (
            "hello",
            "An unrelated sentence.",
            "A greeting.",
            "“_____” means: A greeting.",
        ),
    ],
)
def test_session_uses_masked_fallback_while_generation_is_pending(
    api, word, example, explanation, expected
):
    client, db, owner, _, _ = api
    saved = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": word,
            "english_explanation": explanation,
            "example_sentence": example,
        },
    )
    assert saved.status_code == 201
    response = client.get("/api/v1/reviews/session", headers=owner)
    assert response.status_code == 200
    item = response.json()[0]
    assert item["prompt_sentence"] == expected.strip()
    assert "_____" in item["prompt_sentence"]
    assert normalise_word(word) not in normalise_word(item["prompt_sentence"])
    assert normalise_word(word) not in normalise_word(item["english_explanation"])
    assert "correct_word" not in item and "word" not in item
    assert db.get(Word, uuid.UUID(saved.json()["id"])).example_sentence == example


def test_typing_is_default_and_choice_requires_explicit_authorized_request(api):
    client, db, owner, other, _ = api
    create(client, owner)
    item = client.get("/api/v1/reviews/session", headers=owner).json()[0]
    assert "choices" not in item
    body = {"attempt_id": item["attempt_id"], "review_token": item["review_token"]}
    path = f"/api/v1/reviews/{item['word_id']}/choices"
    assert client.post(path, headers=other, json=body).status_code == 404
    assert (
        client.post(
            path, headers=owner, json={**body, "review_token": "forged"}
        ).status_code
        == 409
    )
    result = client.post(path, headers=owner, json=body)
    assert result.status_code == 200, result.text
    choices = result.json()
    assert len(choices["choices"]) == 4
    assert "Hello" in choices["choices"]
    assert choices["attempt_id"] == item["attempt_id"]
    assert choices["review_token"] == item["review_token"]
    assert choices["prompt_sentence"] == item["prompt_sentence"]
    assert db.scalar(select(func.count()).select_from(ReviewAttempt)) == 0
    client.post(
        f"/api/v1/reviews/{item['word_id']}/answer",
        headers=owner,
        json={**body, "typed_answer": "Hello", "time_taken_ms": 1},
    )
    assert client.post(path, headers=owner, json=body).status_code == 409


def test_review_summary_distinguishes_empty_bank_and_nothing_due(api):
    client, db, owner, other, _ = api
    response = client.get("/api/v1/reviews/summary", headers=owner)
    assert response.status_code == 200
    assert response.json() == {
        "saved_count": 0,
        "due_count": 0,
        "daily_remaining": 50,
        "learned_count": 0,
        "total_count": 0,
    }
    assert response.headers["cache-control"] == "no-store"
    word_id = create(client, owner).json()["id"]
    assert client.get("/api/v1/reviews/summary", headers=owner).json() == {
        "saved_count": 1,
        "due_count": 1,
        "daily_remaining": 50,
        "learned_count": 0,
        "total_count": 1,
    }
    assert (
        client.get("/api/v1/reviews/summary", headers=other).json()["saved_count"] == 0
    )
    client.post(
        f"/api/v1/reviews/{word_id}/answer",
        headers=owner,
        json={"typed_answer": "Hello", "time_taken_ms": 1},
    )
    assert client.get("/api/v1/reviews/summary", headers=owner).json() == {
        "saved_count": 1,
        "due_count": 0,
        "daily_remaining": 50,
        "learned_count": 0,
        "total_count": 1,
    }
    db.get(ReviewState, uuid.UUID(word_id)).due_at = datetime.now(UTC) - timedelta(
        seconds=1
    )
    db.commit()
    prep = client.get("/api/v1/reviews/preparation?source=recall", headers=owner).json()
    assert prep == {
        "saved_count": 1,
        "due_count": 1,
        "daily_remaining": 50,
        "matching_count": 1,
        "count": 1,
    }
    assert client.get("/api/v1/reviews/summary").status_code == 401
