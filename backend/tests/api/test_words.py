"""API contracts for words."""

import uuid

import pytest
from sqlalchemy import func, select

from app.models import ReviewState, User, Word

from .helpers import create


def test_search_marks_only_the_current_users_saved_forms(api):
    client, db, owner, other, _ = api
    assert create(client, owner, " ＣREATE ").status_code == 201
    assert create(client, other, "created").status_code == 201
    response = client.get("/api/v1/words/search?q=create", headers=owner)
    assert response.status_code == 200
    entries = {entry["word"]: entry for entry in response.json()}
    assert entries["create"]["saved"] is True
    assert entries["created"]["saved"] is False
    other_entries = {
        entry["word"]: entry
        for entry in client.get(
            "/api/v1/words/search?q=create",
            headers=other,
        ).json()
    }
    assert other_entries["create"]["saved"] is False
    assert other_entries["created"]["saved"] is True
    assert create(client, owner, "create").status_code == 409
    assert (
        db.scalar(
            select(func.count())
            .select_from(Word)
            .where(
                Word.user_id
                == db.scalar(select(User.id).where(User.email == "owner@example.com")),
            )
        )
        == 1
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"word": "hello"},
        {"english_explanation": "greeting"},
        {"word": None, "english_explanation": "greeting"},
        {"word": "hello", "english_explanation": None},
        {"word": 12, "english_explanation": "greeting"},
        {"word": "hello", "english_explanation": ["greeting"]},
        {"word": "\u3000\t\n", "english_explanation": "greeting"},
        {"word": "hello", "english_explanation": "\u3000\t\n"},
        {"word": "hello", "english_explanation": "x" * 5001},
        {
            "word": "hello",
            "english_explanation": "greeting",
            "user_id": str(uuid.uuid4()),
        },
    ],
)
def test_invalid_word_requests_do_not_write(api, body):
    client, db, owner, _, _ = api
    assert client.post("/api/v1/words", headers=owner, json=body).status_code == 422
    assert db.scalar(select(func.count()).select_from(Word)) == 0
    assert db.scalar(select(func.count()).select_from(ReviewState)) == 0


def test_limits_and_duplicate_rule_preserve_existing_word(api):
    client, db, owner, other, _ = api
    body = {"word": "x" * 200, "english_explanation": "e" * 5000}
    response = client.post("/api/v1/words", headers=owner, json=body)
    assert response.status_code == 201
    word_id = uuid.UUID(response.json()["id"])
    state = db.get(ReviewState, word_id)
    due_at = state.due_at
    assert (
        client.post(
            "/api/v1/words",
            headers=owner,
            json={**body, "word": "X" * 200, "english_explanation": "different"},
        ).status_code
        == 409
    )
    assert db.get(Word, word_id).english_explanation == body["english_explanation"]
    db.refresh(state)
    assert state.due_at == due_at
    assert client.post("/api/v1/words", headers=other, json=body).status_code == 201
    assert len(client.get("/api/v1/reviews/next", headers=owner).json()) == 1
    assert (
        client.post(
            f"/api/v1/reviews/{word_id}/answer",
            headers=owner,
            json={"typed_answer": "X" * 200, "time_taken_ms": 2147483647},
        ).status_code
        == 200
    )


@pytest.mark.parametrize("sentence", [None, "", "   ", "  She showed resilience.  "])
def test_create_word_optional_sentence(api, sentence):
    client, db, owner, _, _ = api
    response = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "resilience",
            "english_explanation": "Recovery",
            "example_sentence": sentence,
        },
    )
    assert response.status_code == 201
    expected = (sentence.strip() or None) if sentence is not None else None
    assert response.json()["example_sentence"] == expected
    assert db.get(Word, uuid.UUID(response.json()["id"])).example_sentence == expected


@pytest.mark.parametrize("sentence", [123, "x" * 5001])
def test_create_word_invalid_sentence(api, sentence):
    client, _, owner, _, _ = api
    response = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": "resilience",
            "english_explanation": "Recovery",
            "example_sentence": sentence,
        },
    )
    assert response.status_code == 422


def test_topic_search_is_deferred_and_tags_are_not_accepted(api):
    client, _, owner, _, _ = api
    assert (
        client.post(
            "/api/v1/words",
            headers=owner,
            json={"word": "word", "english_explanation": "meaning", "topics": ["work"]},
        ).status_code
        == 422
    )
    assert client.get("/api/v1/words/topics", headers=owner).status_code == 404
    for endpoint in ["preparation", "session"]:
        assert (
            client.get(
                f"/api/v1/reviews/{endpoint}?source=topic", headers=owner
            ).status_code
            == 422
        )


@pytest.mark.parametrize("form,spelling", [("V2", "wrote"), ("V3", "written")])
def test_search_form_can_be_saved_and_reviewed_independently(api, form, spelling):
    client, db, owner, other, _ = api
    params = {"q": "write", "parts": "verb", "forms": form}
    response = client.get("/api/v1/words/search", params=params, headers=owner)
    assert response.status_code == 200
    entry = next(item for item in response.json() if item["word"] == spelling)
    assert entry["saved"] is False
    saved = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": entry["word"],
            "english_explanation": entry["english_explanation"],
        },
    )
    assert saved.status_code == 201
    word = db.get(Word, uuid.UUID(saved.json()["id"]))
    assert word.word == spelling
    state = db.get(ReviewState, word.id)
    assert (state.repetitions, state.interval_days, state.ease_factor) == (0, 0, 2.5)
    for headers, expected in [(owner, True), (other, False)]:
        entries = client.get(
            "/api/v1/words/search", params=params, headers=headers
        ).json()
        assert (
            next(item for item in entries if item["word"] == spelling)["saved"]
            is expected
        )
    assert create(client, owner, "write").status_code == 201
    items = client.get("/api/v1/reviews/session", headers=owner).json()
    assert {item["word_id"] for item in items} == {
        saved.json()["id"],
        str(db.scalar(select(Word.id).where(Word.normalised_word == "write"))),
    }
    assert client.get("/api/v1/reviews/session", headers=other).json() == []
