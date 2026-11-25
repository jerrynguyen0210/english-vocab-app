"""Menu inspection, scoped deletion, confirmation and generation integration."""

from datetime import UTC, datetime, timedelta
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app import manage_common_words as menu
from app.core.config import Settings
from app.core.database import Base
from app.models import (
    CommonPracticeQuestion,
    CommonWord,
    User,
    UserCommonWordProgress,
    Word,
)
from app.schemas.common_word_bank import GeneratedBankWord
from app.services.common_word_management import (
    all_word_ids,
    bank_summary,
    browse_words,
    delete_bank_words,
    find_word,
    latest_words,
)


@pytest.fixture
def bank(api_database_url):
    engine = create_engine(api_database_url)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(email="menu@example.test", password_hash="placeholder-test-hash")
        db.add(user)
        db.flush()
        rows = [
            CommonWord(
                word=name,
                normalised_word=name.casefold(),
                part_of_speech="noun",
                english_explanation=f"Meaning of {name}",
                example_sentence=f"An example for {name}.",
                created_at=datetime.now(UTC) + timedelta(seconds=index),
            )
            for index, name in enumerate(["Alpha", "Beta", "Gamma"])
        ]
        db.add_all(rows)
        db.flush()
        ids = [row.id for row in rows]
        for row in rows[:2]:
            db.add(
                UserCommonWordProgress(
                    user_id=user.id, common_word_id=row.id, learned_at=datetime.now(UTC)
                )
            )
            db.add(
                CommonPracticeQuestion(
                    user_id=user.id,
                    common_word_id=row.id,
                    question="Question?",
                    choices=["a", "b", "c", "d"],
                    correct_index=0,
                )
            )
        db.add(
            Word(
                user_id=user.id, word="Alpha", english_explanation="A saved recall word"
            )
        )
        db.commit()
    settings = Settings(
        _env_file=None,
        database_url=api_database_url,
        secret_key="placeholder-test-secret",
        openrouter_model="test/model",
        openrouter_api_key="placeholder-test-key",
    )
    yield engine, settings, ids
    engine.dispose()


def test_counts_latest_and_full_details(bank):
    engine, _, ids = bank
    assert bank_summary(engine) == {
        "words": 3,
        "questions": 2,
        "progress": 2,
        "learned": 2,
    }
    assert [entry.word for entry in latest_words(engine)] == ["Gamma", "Beta", "Alpha"]
    assert find_word(engine, "  ALPHA ").id == ids[0]
    assert find_word(engine, str(ids[0])).meaning == "Meaning of Alpha"
    assert find_word(engine, "missing") is None


def test_latest_is_limited_and_browse_is_paginated_with_literal_search(bank):
    engine, _, _ = bank
    with Session(engine) as db:
        db.add_all(
            [
                CommonWord(
                    word=f"word {i:02}",
                    normalised_word=f"word {i:02}",
                    part_of_speech="noun",
                    english_explanation="Test meaning",
                )
                for i in range(12)
            ]
        )
        db.commit()
    assert len(latest_words(engine)) == 10
    first, cursor = browse_words(engine)
    second, final_cursor = browse_words(engine, after=cursor)
    assert len(first) == 10 and len(second) == 5 and final_cursor is None
    assert not {w.id for w in first}.intersection(w.id for w in second)
    found, _ = browse_words(engine, " ALP ")
    assert [entry.word for entry in found] == ["Alpha"]
    assert browse_words(engine, "%")[0] == []


def test_delete_one_removes_only_its_dependencies_and_keeps_recall(bank):
    engine, _, ids = bank
    result = delete_bank_words(engine, [ids[0], ids[0]])
    assert (result.words, result.questions, result.progress) == (1, 1, 1)
    assert find_word(engine, str(ids[0])) is None
    assert bank_summary(engine) == {
        "words": 2,
        "questions": 1,
        "progress": 1,
        "learned": 1,
    }
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Word)) == 1
        assert db.scalar(select(func.count()).select_from(User)) == 1


def test_clear_uses_confirmed_snapshot_and_preserves_later_insertions(bank):
    engine, _, _ = bank
    snapshot = all_word_ids(engine)
    with Session(engine) as db:
        db.add(
            CommonWord(
                word="Later",
                normalised_word="later",
                part_of_speech="adverb",
                english_explanation="At a later time",
            )
        )
        db.commit()
    assert delete_bank_words(engine, snapshot).words == 3
    assert [entry.word for entry in latest_words(engine)] == ["Later"]
    assert bank_summary(engine)["progress"] == bank_summary(engine)["questions"] == 0


def test_deletion_failure_rolls_back_dependency_deletions(bank, monkeypatch):
    from sqlalchemy.engine import Connection
    from sqlalchemy.sql.dml import Delete

    engine, _, ids = bank
    original = Connection.execute

    def execute(connection, statement, *args, **kwargs):
        if isinstance(statement, Delete) and statement.table.name == "common_words":
            raise SQLAlchemyError("Synthetic deletion failure")
        return original(connection, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "execute", execute)
    with pytest.raises(SQLAlchemyError):
        delete_bank_words(engine, [ids[0]])
    assert bank_summary(engine) == {
        "words": 3,
        "questions": 2,
        "progress": 2,
        "learned": 2,
    }


def inputs(monkeypatch, values):
    values = iter(values)
    monkeypatch.setattr("builtins.input", lambda prompt: next(values))


def test_menu_counts_latest_search_details_and_exit(bank, monkeypatch, capsys):
    engine, settings, _ = bank
    inputs(monkeypatch, ["1", "2", "3", "ALP", "4", "Alpha", "0"])
    menu.run_menu(engine, settings)
    output = capsys.readouterr().out
    assert "Common words: 3" in output and "Meaning of Gamma" in output
    assert "An example for Alpha." in output


@pytest.mark.parametrize(
    "choice,values", [("6", ["Alpha", ""]), ("7", ["wrong confirmation"])]
)
def test_menu_destructive_actions_cancel_without_exact_confirmation(
    bank, monkeypatch, capsys, choice, values
):
    engine, settings, _ = bank
    inputs(monkeypatch, [choice, *values, "0"])
    menu.run_menu(engine, settings)
    assert "Deletion cancelled" in capsys.readouterr().out
    assert bank_summary(engine)["words"] == 3


@pytest.mark.parametrize(
    "values,remaining",
    [(["6", "Alpha", "DELETE Alpha", "0"], 2), (["7", "DELETE ALL 3", "0"], 0)],
)
def test_menu_confirmed_deletion(bank, monkeypatch, values, remaining):
    engine, settings, _ = bank
    inputs(monkeypatch, values)
    menu.run_menu(engine, settings)
    assert bank_summary(engine)["words"] == remaining


def test_menu_generation_reuses_llm_population_and_reports_sql_progress(
    bank, monkeypatch, capsys
):
    engine, settings, _ = bank
    generate = Mock(
        return_value=[
            GeneratedBankWord(
                word="hello",
                part_of_speech="interjection",
                english_explanation="A greeting",
                example_sentence="Say hello.",
                ipa="/test/",
            )
        ]
    )
    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    inputs(monkeypatch, ["5", "1", "", "1", "0"])
    menu.run_menu(engine, settings)
    assert find_word(engine, "hello") is not None
    output = capsys.readouterr().out
    assert "Saved 1/1" in output and "Common words: 4" in output


def test_menu_bad_numeric_input_never_generates_and_stays_open(
    bank, monkeypatch, capsys
):
    engine, settings, _ = bank
    generate = Mock()
    monkeypatch.setattr(menu, "populate_bank", generate)
    inputs(monkeypatch, ["5", "0", "unknown", "0"])
    menu.run_menu(engine, settings)
    generate.assert_not_called()
    assert "Unknown option" in capsys.readouterr().out


def test_main_handles_closed_input_and_disposes_engine(bank, monkeypatch, capsys):
    engine, settings, _ = bank
    monkeypatch.setattr(menu, "get_engine", lambda: engine)
    monkeypatch.setattr(menu, "get_settings", lambda: settings)
    monkeypatch.setattr("sys.argv", ["manage_common_words"])

    def closed(prompt):
        raise EOFError()

    monkeypatch.setattr("builtins.input", closed)
    menu.main()
    assert "Menu closed" in capsys.readouterr().out


def repair_entry(word):
    return GeneratedBankWord(
        word=word,
        part_of_speech="noun",
        english_explanation="Replacement meaning",
        example_sentence="Replacement example.",
        ipa="/test/",
    )


def test_inspection_decline_never_calls_llm(bank, monkeypatch, capsys):
    engine, settings, _ = bank
    repair = Mock()
    monkeypatch.setattr(menu, "repair_bank", repair)
    inputs(monkeypatch, ["8", "", "0"])
    menu.run_menu(engine, settings)
    repair.assert_not_called()
    assert "Missing optional: ipa: 3" in capsys.readouterr().out


def test_menu_repairs_missing_ipa_and_reinspects_without_changing_history(
    bank, monkeypatch, capsys
):
    engine, settings, ids = bank
    repair = Mock(
        side_effect=lambda words, **kwargs: [repair_entry(w["word"]) for w in words]
    )
    monkeypatch.setattr("app.services.common_word_repair.repair_bank_words", repair)
    inputs(monkeypatch, ["8", "yes", "0"])
    menu.run_menu(engine, settings)
    assert repair.call_count == 1
    output = capsys.readouterr().out
    assert "Saved repairs for 3 Common words" in output
    assert "No duplicates, missing values" in output
    alpha = find_word(engine, str(ids[0]))
    assert alpha.ipa == "/test/"
    assert alpha.meaning == "Meaning of Alpha"
    assert alpha.example == "An example for Alpha."
    assert bank_summary(engine) == {
        "words": 3,
        "questions": 2,
        "progress": 2,
        "learned": 2,
    }
    # A clean inspection should not prompt for repair.
    inputs(monkeypatch, ["8", "0"])
    menu.run_menu(engine, settings)
    assert repair.call_count == 1


@pytest.mark.parametrize("failure", ["identity", "missing", "provider"])
def test_invalid_repairs_leave_content_unchanged_and_menu_open(
    bank, monkeypatch, capsys, failure
):
    from app.llm.openrouter_review import ReviewError

    engine, settings, _ = bank

    def response(words, **kwargs):
        if failure == "provider":
            raise ReviewError("Synthetic failure", "provider_connection")
        if failure == "missing":
            return []
        return [repair_entry("different") for word in words]

    monkeypatch.setattr("app.services.common_word_repair.repair_bank_words", response)
    inputs(monkeypatch, ["8", "y", "1", "0"])
    menu.run_menu(engine, settings)
    assert all(word.ipa is None for word in latest_words(engine))
    output = capsys.readouterr().out
    assert "LLM repair failed" in output
    assert "Common words: 3" in output


def test_repairs_all_findings_beyond_inspection_sample_and_keeps_completed_batches(
    bank, monkeypatch
):
    from app.llm.openrouter_review import ReviewError
    from app.services.common_word_management import inspect_bank
    from app.services.common_word_repair import repair_bank

    engine, settings, _ = bank
    with Session(engine) as db:
        db.add_all(
            [
                CommonWord(
                    word="word " + chr(97 + i),
                    normalised_word="word " + chr(97 + i),
                    part_of_speech="noun",
                    english_explanation="Meaning",
                )
                for i in range(22)
            ]
        )
        db.commit()
    calls = []

    def response(words, **kwargs):
        calls.append(words)
        if len(calls) == 2:
            raise ReviewError("Synthetic failure", "provider_connection")
        return [repair_entry(w["word"]) for w in words]

    monkeypatch.setattr("app.services.common_word_repair.repair_bank_words", response)
    with pytest.raises(ReviewError):
        repair_bank(engine, settings)
    assert [len(call) for call in calls] == [20, 5]
    assert inspect_bank(engine).counts["Missing optional: ipa"] == 5
    calls.clear()
    assert repair_bank(engine, settings) == 5
    assert not inspect_bank(engine).counts


def test_repair_detects_invalid_content_and_preserves_concurrent_edits(
    bank, monkeypatch
):
    from app.services.common_word_management import inspect_bank
    from app.services.common_word_repair import repair_bank

    engine, settings, ids = bank
    with Session(engine) as db:
        alpha = db.get(CommonWord, ids[0])
        alpha.ipa = "invalid IPA"
        alpha.part_of_speech = ""
        db.commit()
    report = inspect_bank(engine)
    assert report.counts["Invalid content: ipa"] == 1
    assert report.counts["Missing required: part_of_speech"] == 1

    def response(words, **kwargs):
        with Session(engine) as db:
            beta = db.get(CommonWord, ids[1])
            beta.english_explanation = "Concurrent edit"
            db.commit()
        return [repair_entry(w["word"]) for w in words]

    monkeypatch.setattr("app.services.common_word_repair.repair_bank_words", response)
    assert repair_bank(engine, settings) == 2
    assert find_word(engine, str(ids[0])).ipa == "/test/"
    assert find_word(engine, str(ids[0])).part_of_speech == "noun"
    beta = find_word(engine, str(ids[1]))
    assert beta.meaning == "Concurrent edit" and beta.ipa is None
