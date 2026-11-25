"""Shared bank selection, private answers, ownership, learning and recall integration."""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.export_user import collect_user_data
from app.llm.openrouter_review import ReviewError
from app.models import (
    CommonPracticeQuestion,
    CommonWord,
    PromptJob,
    ReviewState,
    UserCommonWordProgress,
    Word,
)
from app.schemas.common_words import GeneratedCommonQuestion
from app.services.teachers import TEACHERS

BATCH = "/api/v1/common-words/batch"
BANK_SIZE = 40


@pytest.fixture(autouse=True)
def operator_bank(api):
    _, db, *_ = api
    assert count(db, CommonWord) == 0
    db.add_all(
        [
            CommonWord(
                id=uuid.UUID(int=i + 1),
                word=f"Test word {i}",
                normalised_word=f"test word {i}",
                part_of_speech="noun",
                english_explanation=f"Test meaning {i}",
            )
            for i in range(BANK_SIZE)
        ]
    )
    db.commit()


def generated(words):
    return [
        GeneratedCommonQuestion(
            common_word_id=w.id,
            question=f"What does {w.word} mean?",
            choices=[
                w.english_explanation,
                "Something unrelated",
                "Another unrelated meaning",
                "A different meaning",
            ],
            correct_index=0,
        )
        for w in words
    ]


@pytest.fixture
def generator(monkeypatch):
    calls = []

    def generate(words, **kwargs):
        calls.append(words)
        return generated(words)

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    return calls


def batch(api):
    client, _, owner, *_ = api
    response = client.post(BATCH, headers=owner, json={})
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()["questions"]


def answer(client, owner, question, index=0):
    return client.post(
        f"/api/v1/common-words/questions/{question['id']}/answer",
        headers=owner,
        json={"selected_index": index},
    )


def owner_id(client, owner):
    return uuid.UUID(client.get("/api/v1/auth/me", headers=owner).json()["id"])


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_populated_bank_generates_ten_owned_questions_without_answer_keys(
    api, generator
):
    client, db, owner, *_ = api
    assert count(db, CommonWord) == BANK_SIZE
    questions = batch(api)
    assert len(questions) == 10 and len(generator) == 1
    assert len({w.id for w in generator[0]}) == 10
    assert all(
        "correctIndex" not in q
        and "correct_index" not in q
        and len(q["choices"]) == 4
        and q["question"]
        for q in questions
    )
    assert count(db, CommonPracticeQuestion) == count(db, UserCommonWordProgress) == 10
    assert count(db, Word) == count(db, PromptJob) == 0
    assert (
        client.get("/api/v1/reviews/summary", headers=owner).json()["learned_count"]
        == 0
    )


def test_selection_pages_past_learned_words_and_keeps_saved_unlearned_words(
    api, generator
):
    client, db, owner, *_ = api
    user_id = owner_id(client, owner)
    words = list(db.scalars(select(CommonWord).order_by(CommonWord.id)))
    db.add_all(
        [
            UserCommonWordProgress(
                user_id=user_id, common_word_id=w.id, learned_at=datetime.now(UTC)
            )
            for w in words[:27]
        ]
    )
    db.add(
        Word(
            user_id=user_id,
            word=words[27].word,
            english_explanation=words[27].english_explanation,
        )
    )
    db.commit()
    questions = batch(api)
    assert [w.id for w in generator[0]] == [w.id for w in words[27:37]]
    assert questions[0]["word"] == words[27].word


def test_correct_answer_is_idempotent_user_scoped_and_excluded_from_next_batch(
    api, generator
):
    client, db, owner, other, *_ = api
    question = batch(api)[0]
    response = answer(client, owner, question)
    assert response.json()["result"] == "correct"
    progress = db.scalar(
        select(UserCommonWordProgress).where(
            UserCommonWordProgress.learned_at.is_not(None)
        )
    )
    learned_at = progress.learned_at
    assert answer(client, owner, question).json() == response.json()
    db.refresh(progress)
    assert progress.learned_at == learned_at
    assert answer(client, owner, question, 1).status_code == 409
    assert answer(client, other, question).status_code == 404
    assert question["word"] not in [q["word"] for q in batch(api)]
    assert count(db, Word) == 0
    assert (
        client.get("/api/v1/reviews/summary", headers=owner).json()["learned_count"]
        == 1
    )
    assert (
        client.get("/api/v1/reviews/summary", headers=other).json()["learned_count"]
        == 0
    )


def test_incorrect_answer_and_explicit_save_do_not_mark_learned(api, generator):
    client, db, owner, *_ = api
    question = batch(api)[0]
    response = answer(client, owner, question, 1)
    assert (
        response.json()["result"] == "incorrect"
        and response.json()["correctIndex"] == 0
    )
    assert count(db, Word) == 0
    saved = client.post(
        "/api/v1/words",
        headers=owner,
        json={
            "word": question["word"],
            "english_explanation": question["explanation"],
            "example_sentence": question["example"],
        },
    )
    assert saved.status_code == 201
    assert count(db, ReviewState) == count(db, PromptJob) == 1
    assert (
        db.scalar(
            select(func.count())
            .select_from(UserCommonWordProgress)
            .where(UserCommonWordProgress.learned_at.is_not(None))
        )
        == 0
    )
    new_question = next(q for q in batch(api) if q["word"] == question["word"])
    answer(client, owner, new_question)
    summary = client.get("/api/v1/reviews/summary", headers=owner).json()
    assert (
        summary["saved_count"]
        == summary["learned_count"]
        == summary["total_count"]
        == 1
    )


def test_final_partial_batch_and_completion_do_not_generate_extra_words(api, generator):
    client, db, owner, *_ = api
    user_id = owner_id(client, owner)
    words = list(db.scalars(select(CommonWord).order_by(CommonWord.id)))
    db.add_all(
        [
            UserCommonWordProgress(
                user_id=user_id, common_word_id=w.id, learned_at=datetime.now(UTC)
            )
            for w in words[:-3]
        ]
    )
    db.commit()
    questions = batch(api)
    assert len(questions) == len(generator[0]) == 3
    for question in questions:
        assert answer(client, owner, question).status_code == 200
    assert client.post(BATCH, headers=owner, json={}).json() == {
        "status": "complete",
        "questions": [],
    }
    assert len(generator) == 1


@pytest.mark.parametrize("failure", ["provider", "partial", "duplicates", "wrong_ids"])
def test_generation_failure_never_persists_partial_questions(api, monkeypatch, failure):
    client, db, owner, *_ = api

    def generate(words, **kwargs):
        assert not db.in_transaction(), "LLM I/O must not hold a database transaction"
        if failure == "provider":
            raise ReviewError("Provider body must stay private")
        rows = generated(words)
        if failure == "partial":
            return rows[:-1]
        if failure == "duplicates":
            return [rows[0]] * 10
        rows[0].common_word_id = uuid.uuid4()
        return rows

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    response = client.post(BATCH, headers=owner, json={})
    assert response.status_code == 503 and "Provider body" not in response.text
    assert count(db, CommonPracticeQuestion) == count(db, UserCommonWordProgress) == 0


def test_generation_rechecks_concurrent_learning_outside_transaction(api, monkeypatch):
    client, db, owner, *_ = api
    user_id = owner_id(client, owner)
    calls = []

    def generate(words, **kwargs):
        assert not db.in_transaction()
        calls.append(words)
        if len(calls) == 1:
            with Session(db.get_bind()) as concurrent:
                concurrent.add(
                    UserCommonWordProgress(
                        user_id=user_id,
                        common_word_id=words[0].id,
                        learned_at=datetime.now(UTC),
                    )
                )
                concurrent.commit()
        return generated(words)

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    questions = batch(api)
    assert len(calls) == 2
    assert calls[0][0].word not in [q["word"] for q in questions]
    assert count(db, CommonPracticeQuestion) == 10


def test_generation_after_account_deletion_cannot_restore_data(api, monkeypatch):
    client, db, owner, *_ = api

    def generate(words, **kwargs):
        assert client.delete("/api/v1/account", headers=owner).status_code == 204
        return generated(words)

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    assert client.post(BATCH, headers=owner, json={}).status_code == 401
    assert count(db, CommonPracticeQuestion) == 0 and count(db, CommonWord) == BANK_SIZE


def test_export_and_erasure_include_owned_common_data_and_preserve_shared_bank(
    api, generator
):
    client, db, owner, other, *_ = api
    user_id = owner_id(client, owner)
    questions = batch(api)
    answer(client, owner, questions[0])
    exported = collect_user_data(db, user_id)
    assert (
        len(exported["common_word_progress"])
        == len(exported["common_practice_questions"])
        == 10
    )
    assert any(row["learned_at"] for row in exported["common_word_progress"])
    assert collect_user_data(db, owner_id(client, other))["common_word_progress"] == []
    assert client.delete("/api/v1/account", headers=owner).status_code == 204
    assert count(db, UserCommonWordProgress) == count(db, CommonPracticeQuestion) == 0
    assert count(db, CommonWord) == BANK_SIZE


@pytest.mark.parametrize(
    "body",
    [
        {"selected_index": True},
        {"selected_index": 4},
        {"selected_index": -1},
        {"selected_index": "0"},
        {},
        {"selected_index": 0, "correct_index": 0},
    ],
)
def test_answer_validation(api, generator, body):
    client, _, owner, *_ = api
    question = batch(api)[0]
    assert (
        client.post(
            f"/api/v1/common-words/questions/{question['id']}/answer",
            headers=owner,
            json=body,
        ).status_code
        == 422
    )


def test_common_endpoints_require_auth_and_strict_batch_body(api, generator):
    client, _, owner, *_ = api
    assert client.post(BATCH, json={}).status_code == 401
    assert (
        client.post(
            f"/api/v1/common-words/questions/{uuid.uuid4()}/answer",
            json={"selected_index": 0},
        ).status_code
        == 401
    )
    assert (
        client.post(BATCH, headers=owner, json={"exclude_ids": []}).status_code == 422
    )
    assert not generator


def test_postgres_concurrent_answer_replays_are_atomic(api, generator):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from app.models import User
    from app.services.common_words import answer_question

    client, db, owner, *_ = api
    if db.get_bind().dialect.name != "postgresql":
        pytest.skip("Concurrent row locking requires PostgreSQL")
    question = batch(api)[0]
    user_id = owner_id(client, owner)
    db.commit()
    barrier = Barrier(2)
    engine = db.get_bind()

    def submit():
        with Session(engine) as session:
            user = session.get(User, user_id)
            barrier.wait(timeout=5)
            return answer_question(session, user, uuid.UUID(question["id"]), 0)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    assert results[0].result == "correct"
    assert (
        db.scalar(
            select(func.count())
            .select_from(UserCommonWordProgress)
            .where(UserCommonWordProgress.learned_at.is_not(None))
        )
        == 1
    )


@pytest.mark.parametrize("action", ["delete", "disable"])
def test_generation_rechecks_account_changed_by_an_independent_session(
    api, monkeypatch, action
):
    from app.models import User
    from app.services.accounts import delete_account

    client, db, owner, *_ = api
    user_id = owner_id(client, owner)

    def generate(words, **kwargs):
        with Session(db.get_bind()) as other:
            user = other.get(User, user_id)
            if action == "delete":
                delete_account(other, user)
            else:
                user.disabled_at = datetime.now(UTC)
                other.commit()
        return generated(words)

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    response = client.post(BATCH, headers=owner, json={})
    assert response.status_code == 401
    assert count(db, CommonPracticeQuestion) == count(db, UserCommonWordProgress) == 0
    assert count(db, CommonWord) == BANK_SIZE


def test_empty_operator_bank_is_unavailable_not_all_learned(api, generator):
    client, db, owner, *_ = api
    db.execute(delete(CommonWord))
    db.commit()
    response = client.post(BATCH, headers=owner, json={})
    assert response.status_code == 503
    assert not generator


@pytest.mark.parametrize("selected_teacher", TEACHERS, ids=lambda teacher: teacher.id)
def test_common_question_generation_uses_the_accounts_teacher(
    api, monkeypatch, selected_teacher
):
    from unittest.mock import Mock

    client, _, owner, other, _ = api
    generator = Mock(side_effect=lambda words, **kwargs: generated(words))
    monkeypatch.setattr(
        "app.services.common_words.generate_common_questions", generator
    )
    other_teacher = next(entry for entry in TEACHERS if entry.id != selected_teacher.id)
    for headers, teacher in ((owner, selected_teacher), (other, other_teacher)):
        response = client.put(
            "/api/v1/teachers/selection",
            headers=headers,
            json={"teacher_id": teacher.id},
        )
        assert response.status_code == 200
        assert client.post(BATCH, headers=headers, json={}).status_code == 200
        assert generator.call_args.kwargs["model"] == teacher.model


@pytest.mark.parametrize("teacher", TEACHERS[1:], ids=lambda teacher: teacher.id)
def test_teacher_change_during_common_generation_retries_with_new_model(
    api, monkeypatch, teacher
):
    from app.models import User
    from app.services.teachers import select_teacher

    client, db, owner, *_ = api
    user_id = owner_id(client, owner)
    with Session(db.get_bind()) as independent:
        select_teacher(independent, independent.get(User, user_id), TEACHERS[0].id)
    models = []

    def generate(words, **kwargs):
        models.append(kwargs["model"])
        if len(models) == 1:
            with Session(db.get_bind()) as independent:
                select_teacher(independent, independent.get(User, user_id), teacher.id)
        return generated(words)

    monkeypatch.setattr("app.services.common_words.generate_common_questions", generate)
    assert client.post(BATCH, headers=owner, json={}).status_code == 200
    assert models == [TEACHERS[0].model, teacher.model]
    assert count(db, CommonPracticeQuestion) == 10
