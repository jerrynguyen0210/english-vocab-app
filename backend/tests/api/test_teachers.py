"""Per-user teacher preferences and selected-model question generation."""

import uuid
from unittest.mock import Mock

from sqlalchemy.orm import Session

from app.models import PromptJob, ReviewState, User, Word
from app.services.prompt_jobs.worker import claim_job, finish_job, process_one
from app.services.teachers import TEACHERS

from .helpers import create


def choose(client, headers, teacher_id):
    return client.put(
        "/api/v1/teachers/selection", headers=headers, json={"teacher_id": teacher_id}
    )


def test_teacher_directory_and_per_user_persistence(api):
    client, db, owner, other, _ = api
    response = client.get("/api/v1/teachers", headers=owner)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "teachers": [
            {
                "id": "teacher-01",
                "name": "Emma Wilson",
                "model": "openai/gpt-oss-20b",
            },
            {
                "id": "teacher-02",
                "name": "James Bennett",
                "model": "openai/gpt-oss-120b",
            },
        ],
        "selected_teacher_id": None,
    }
    for headers, teacher in ((owner, TEACHERS[0]), (other, TEACHERS[1])):
        saved = choose(client, headers, teacher.id)
        assert saved.status_code == 200
        assert saved.json() == {"teacher_id": teacher.id}
        assert saved.headers["cache-control"] == "no-store"
        assert (
            client.get("/api/v1/teachers", headers=headers).json()[
                "selected_teacher_id"
            ]
            == teacher.id
        )
        user_id = uuid.UUID(client.get("/api/v1/auth/me", headers=headers).json()["id"])
        with Session(db.get_bind()) as independent:
            assert independent.get(User, user_id).selected_teacher_id == teacher.id


def test_teacher_endpoints_require_authentication(api):
    client, *_ = api
    assert client.get("/api/v1/teachers").status_code == 401
    assert choose(client, {}, TEACHERS[0].id).status_code == 401


def test_teacher_selection_rejects_unknown_models_and_other_user_fields(api):
    client, _, owner, _, _ = api
    for body in (
        {},
        {"teacher_id": ""},
        {"teacher_id": "x" * 129},
        {"teacher_id": TEACHERS[0].id, "user_id": "another-user"},
        {"teacher_id": "openai/gpt-oss-120b"},
        {"teacher_id": "unknown"},
    ):
        assert (
            client.put(
                "/api/v1/teachers/selection", headers=owner, json=body
            ).status_code
            == 422
        )
    assert (
        client.get("/api/v1/teachers", headers=owner).json()["selected_teacher_id"]
        is None
    )


def test_prompt_worker_uses_each_owners_selected_model(api, monkeypatch):
    client, db, owner, other, _ = api
    words = []
    for headers, teacher in ((owner, TEACHERS[0]), (other, TEACHERS[1])):
        assert choose(client, headers, teacher.id).status_code == 200
        words.append(uuid.UUID(create(client, headers).json()["id"]))
    generator = Mock(
        side_effect=lambda *args, **kwargs: {
            "prompt_sentence": f"Model {kwargs['model']} says _____.",
        }
    )
    monkeypatch.setattr("app.services.prompt_jobs.worker.generate_review", generator)
    db.rollback()
    assert process_one(db.get_bind())
    assert process_one(db.get_bind())
    assert {call.kwargs["model"] for call in generator.call_args_list} == {
        teacher.model for teacher in TEACHERS
    }
    db.expire_all()
    for word_id, teacher, headers in zip(words, TEACHERS, (owner, other)):
        assert (
            db.get(Word, word_id).review_prompt == f"Model {teacher.model} says _____."
        )
        # Review by time and recall share the same selected-model prompt.
        for source in ("time", "recall"):
            response = client.get(
                f"/api/v1/reviews/session?source={source}", headers=headers
            )
            assert response.status_code == 200
            assert (
                response.json()[0]["prompt_sentence"]
                == f"Model {teacher.model} says _____."
            )
    assert generator.call_count == 2  # Session reads never invoke a model.


def test_changing_teacher_requeues_only_owned_words_and_fences_old_worker(
    api, monkeypatch
):
    client, db, owner, other, _ = api
    choose(client, owner, TEACHERS[0].id)
    word_id = uuid.UUID(create(client, owner).json()["id"])
    db.rollback()
    claimed = claim_job(db.get_bind())
    assert claimed is not None and claimed.model == TEACHERS[0].model
    other_word_id = uuid.UUID(create(client, other).json()["id"])
    other_job = db.get(PromptJob, other_word_id)
    other_job.attempts = 2
    db.commit()
    state_before = db.get(ReviewState, word_id).due_at
    prompt_before = db.get(Word, word_id).review_prompt
    assert choose(client, owner, TEACHERS[1].id).status_code == 200
    db.expire_all()
    replacement = db.get(PromptJob, word_id)
    assert replacement.attempts == 0 and replacement.lease_token is None
    assert db.get(PromptJob, other_word_id).attempts == 2
    assert db.get(ReviewState, word_id).due_at == state_before
    db.rollback()
    finish_job(db.get_bind(), claimed, "Stale model says _____.")
    db.expire_all()
    assert db.get(Word, word_id).review_prompt == prompt_before
    assert db.get(PromptJob, word_id) is not None
    generator = Mock(return_value={"prompt_sentence": "New teacher says _____."})
    monkeypatch.setattr("app.services.prompt_jobs.worker.generate_review", generator)
    # Process all pending work; only the selected account uses the second model.
    db.rollback()
    while process_one(db.get_bind()):
        pass
    db.expire_all()
    assert db.get(Word, word_id).review_prompt == "New teacher says _____."
    assert any(
        call.kwargs["model"] == TEACHERS[1].model for call in generator.call_args_list
    )
    assert choose(client, owner, TEACHERS[1].id).status_code == 200
    assert db.get(PromptJob, word_id, populate_existing=True) is None
