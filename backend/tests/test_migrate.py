"""Deployment upgrades are repeatable and errors stop API startup."""

import os
import subprocess

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.migrate import upgrade_database


def test_common_word_removal_migration_preserves_account_and_saved_words(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path}/common-learning.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0017")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:owner, 'legacy@example.test', 'placeholder')"
                ),
                {"owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO common_word_questions "
                    "(id, user_id, word, normalised_word, part_of_speech, explanation, example, choices, correct_index) "
                    "VALUES (:question, :owner, 'hello', 'hello', 'interjection', 'A greeting', 'Say hello.', :choices, 0)"
                ),
                {
                    "question": "2" * 32,
                    "owner": "1" * 32,
                    "choices": '["A greeting", "A colour", "A number", "A place"]',
                },
            )
        command.upgrade(config, "0019")
        with engine.connect() as connection:
            assert tuple(
                connection.execute(
                    text(
                        "SELECT word, correct_index, learned_at, ipa FROM common_word_questions"
                    )
                ).one()
            ) == ("hello", 0, None, None)
        with engine.begin() as connection:
            connection.execute(
                text("INSERT INTO common_word_jobs (user_id) VALUES (:owner)"),
                {"owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO words (id, user_id, word, normalised_word, english_explanation) "
                    "VALUES (:word, :owner, 'saved', 'saved', 'Kept vocabulary')"
                ),
                {"word": "3" * 32, "owner": "1" * 32},
            )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            tables = inspect(connection).get_table_names()
            assert "common_word_questions" not in tables
            assert "common_word_jobs" not in tables
            assert (
                connection.scalar(text("SELECT email FROM users"))
                == "legacy@example.test"
            )
            assert connection.scalar(text("SELECT word FROM words")) == "saved"
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_response_and_failure_migrations_preserve_existing_data(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/response-snapshots.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0013")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:owner, 'legacy@example.test', 'placeholder')"
                ),
                {"owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO words (id, user_id, word, normalised_word, english_explanation) "
                    "VALUES (:word, :owner, 'hello', 'hello', 'A greeting')"
                ),
                {"word": "2" * 32, "owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO review_attempts (id, word_id, user_id, typed_answer, normalised_answer, result, time_taken_ms) "
                    "VALUES (:attempt, :word, :owner, 'Hello', 'hello', 'correct', 10)"
                ),
                {"attempt": "3" * 32, "word": "2" * 32, "owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO prompt_jobs (word_id, attempts, lease_token) VALUES (:word, 3, :token)"
                ),
                {"word": "2" * 32, "token": "4" * 32},
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert tuple(
                connection.execute(
                    text(
                        "SELECT typed_answer, result, next_due_at FROM review_attempts"
                    )
                ).one()
            ) == ("Hello", "correct", None)
            assert tuple(
                connection.execute(
                    text(
                        "SELECT attempts, lease_token, failed_at, failure_category FROM prompt_jobs"
                    )
                ).one()
            ) == (3, "4" * 32, None, None)
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_upgrade_and_repeated_run(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/deploy.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        command.upgrade(Config("alembic.ini"), "0007")
        engine = create_engine(url)
        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:id, :email, :hash)"
                ),
                {
                    "id": "1" * 32,
                    "email": "existing@example.com",
                    "hash": "placeholder-hash",
                },
            )
        engine.dispose()
        upgrade_database()
        upgrade_database()
        engine = create_engine(url)
        with engine.connect() as conn:
            assert (
                conn.scalar(text("SELECT version_num FROM alembic_version"))
                == ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()
            )
            assert (
                conn.scalar(
                    text("SELECT name FROM users WHERE email = 'existing@example.com'")
                )
                is None
            )
            conn.execute(
                text(
                    "UPDATE users SET name = 'Alex' WHERE email = 'existing@example.com'"
                )
            )
            assert (
                conn.scalar(
                    text("SELECT name FROM users WHERE email = 'existing@example.com'")
                )
                == "Alex"
            )
        engine.dispose()
    finally:
        get_settings.cache_clear()


def test_entrypoint_stops_on_migration_failure(tmp_path):
    python = tmp_path / "python"
    python.write_text("#!/bin/sh\nexit 17\n")
    python.chmod(0o755)
    result = subprocess.run(
        ["sh", "entrypoint.sh", "sh", "-c", "echo API_STARTED"],
        env={**os.environ, "PATH": f"{tmp_path}:/usr/bin:/bin"},
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 17
    assert "API_STARTED" not in result.stdout


def test_preparation_migration_preserves_existing_schedule_and_history(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path}/preparation.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    command.upgrade(config, "0009")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO users (id, email, password_hash) VALUES (:id, 'migration@example.test', 'placeholder')"
            ),
            {"id": "1" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO words (id, user_id, word, normalised_word, english_explanation) VALUES (:id, :owner, 'word', 'word', 'Meaning')"
            ),
            {"id": "2" * 32, "owner": "1" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO review_states (word_id, level, due_at, correct_count, incorrect_count) VALUES (:id, 4, '2026-12-10 12:00:00', 5, 2)"
            ),
            {"id": "2" * 32},
        )
        connection.execute(
            text(
                "INSERT INTO review_attempts (id, word_id, user_id, typed_answer, normalised_answer, result, time_taken_ms) VALUES (:id, :word, :owner, 'word', 'word', 'correct', 123)"
            ),
            {"id": "3" * 32, "word": "2" * 32, "owner": "1" * 32},
        )
    command.upgrade(config, "head")
    with engine.connect() as connection:
        state = connection.execute(
            text(
                "SELECT level, due_at, correct_count, incorrect_count, repetitions, interval_days, ease_factor FROM review_states"
            )
        ).one()
        assert tuple(state) == (4, "2026-12-10 12:00:00", 5, 2, 0, 0, 2.5)
        assert connection.scalar(text("SELECT count(*) FROM review_attempts")) == 1
        assert (
            connection.scalar(text("SELECT next_due_at FROM review_attempts")) is None
        )
        assert "word_topics" not in inspect(connection).get_table_names()
        assert (
            connection.scalar(text("SELECT review_prompt FROM words"))
            == "“_____” means: Meaning"
        )
    engine.dispose()
    get_settings.cache_clear()


def test_stored_prompt_migration_masks_legacy_examples(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/prompts.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0011")
        cases = [
            (
                "straße",
                "A road.",
                "Try ＳＴＲＡＳＳＥ and Straße.",
                "Try _____ and _____.",
            ),
            (
                "take a break",
                "To pause.",
                "We take\na break at noon.",
                "We _____ at noon.",
            ),
            (
                "hello",
                "Hello is a greeting.",
                None,
                "“_____” means: _____ is a greeting.",
            ),
        ]
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:id, 'legacy@example.test', 'placeholder')"
                ),
                {"id": "1" * 32},
            )
            for index, (word, meaning, example, _) in enumerate(cases, start=2):
                connection.execute(
                    text(
                        "INSERT INTO words (id, user_id, word, normalised_word, english_explanation, example_sentence) "
                        "VALUES (:id, :owner, :word, :word, :meaning, :example)"
                    ),
                    {
                        "id": str(index) * 32,
                        "owner": "1" * 32,
                        "word": word,
                        "meaning": meaning,
                        "example": example,
                    },
                )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            rows = connection.execute(
                text("SELECT example_sentence, review_prompt FROM words ORDER BY id")
            ).all()
            assert [tuple(row) for row in rows] == [
                (case[2], case[3]) for case in cases
            ]
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_operator_common_bank_upgrade_is_empty_repeatable_and_matches_models(
    tmp_path, monkeypatch
):
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from app.core.database import Base

    url = f"sqlite:///{tmp_path}/shared-common.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0020")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            original_ids = (
                connection.execute(text("SELECT id FROM common_words ORDER BY id"))
                .scalars()
                .all()
            )
            assert len(original_ids) == 0
            assert (
                connection.scalar(
                    text("SELECT count(DISTINCT normalised_word) FROM common_words")
                )
                == 0
            )
            assert (
                compare_metadata(
                    MigrationContext.configure(
                        connection,
                        opts={
                            "include_object": lambda obj, name, kind, reflected, compared: (
                                name
                                in {
                                    "common_words",
                                    "common_practice_questions",
                                    "user_common_word_progress",
                                }
                                if kind == "table"
                                else obj.table.name
                                in {
                                    "common_words",
                                    "common_practice_questions",
                                    "user_common_word_progress",
                                }
                            )
                        },
                    ),
                    Base.metadata,
                )
                == []
            )
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT id FROM common_words ORDER BY id"))
                .scalars()
                .all()
                == original_ids
            )
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_remove_bundled_content_keeps_operator_bank_and_saved_recall(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path}/remove-bundled.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0021")
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT count(*) FROM common_words")) == 1000
            seed_id = connection.scalar(text("SELECT id FROM common_words LIMIT 1"))
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:owner, 'operator-test@example.test', 'placeholder-test-hash')"
                ),
                {"owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO words (id, user_id, word, normalised_word, english_explanation) VALUES (:id, :owner, 'saved', 'saved', 'Existing recall')"
                ),
                {"id": "2" * 32, "owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO common_words (id, word, normalised_word, part_of_speech, english_explanation) VALUES (:id, 'operator word', 'operator word', 'noun', 'Operator generated')"
                ),
                {"id": "3" * 32},
            )
            for index, word_id in enumerate([seed_id, "3" * 32], start=4):
                connection.execute(
                    text(
                        "INSERT INTO user_common_word_progress (user_id, common_word_id, learned_at) VALUES (:owner, :word, '2026-11-24 00:00:00')"
                    ),
                    {"owner": "1" * 32, "word": word_id},
                )
                connection.execute(
                    text(
                        "INSERT INTO common_practice_questions (id, user_id, common_word_id, question, choices, correct_index) VALUES (:id, :owner, :word, 'Question', :choices, 0)"
                    ),
                    {
                        "id": str(index) * 32,
                        "owner": "1" * 32,
                        "word": word_id,
                        "choices": '["one", "two", "three", "four"]',
                    },
                )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM common_words")) == 1
            assert (
                connection.scalar(text("SELECT word FROM common_words"))
                == "operator word"
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM user_common_word_progress")
                )
                == 1
            )
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM common_practice_questions")
                )
                == 1
            )
            assert connection.scalar(text("SELECT word FROM words")) == "saved"
            assert connection.scalar(text("SELECT count(*) FROM users")) == 1
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_teacher_preference_upgrade_preserves_accounts_words_and_jobs(
    tmp_path, monkeypatch
):
    url = f"sqlite:///{tmp_path}/teacher-preference.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    try:
        command.upgrade(config, "0023")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO users (id, email, password_hash) VALUES (:owner, 'teacher-migration@example.test', 'placeholder')"
                ),
                {"owner": "1" * 32},
            )
            connection.execute(
                text(
                    "INSERT INTO words (id, user_id, word, normalised_word, english_explanation, review_prompt) "
                    "VALUES (:word, :owner, 'hello', 'hello', 'A greeting', 'Say _____.')"
                ),
                {"word": "2" * 32, "owner": "1" * 32},
            )
            connection.execute(
                text("INSERT INTO prompt_jobs (word_id, attempts) VALUES (:word, 2)"),
                {"word": "2" * 32},
            )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT selected_teacher_id FROM users")) is None
            )
            assert (
                connection.scalar(text("SELECT review_prompt FROM words"))
                == "Say _____."
            )
            assert connection.scalar(text("SELECT attempts FROM prompt_jobs")) == 2
    finally:
        engine.dispose()
        get_settings.cache_clear()


def test_teacher_id_rename_preserves_existing_selections(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/rename-teachers.db"
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    config = Config("alembic.ini")
    engine = create_engine(url)
    selections = ["suggested-name-01", "suggested-name-02", None, "teacher-01"]
    try:
        command.upgrade(config, "0024")
        with engine.begin() as connection:
            for index, selection in enumerate(selections, start=1):
                connection.execute(
                    text(
                        "INSERT INTO users (id, email, password_hash, selected_teacher_id) "
                        "VALUES (:id, :email, 'placeholder', :selection)"
                    ),
                    {
                        "id": str(index) * 32,
                        "email": f"teacher-rename-{index}@example.test",
                        "selection": selection,
                    },
                )
        command.upgrade(config, "head")
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT selected_teacher_id FROM users ORDER BY email")
            ).scalars().all() == ["teacher-01", "teacher-02", None, "teacher-01"]
    finally:
        engine.dispose()
        get_settings.cache_clear()
