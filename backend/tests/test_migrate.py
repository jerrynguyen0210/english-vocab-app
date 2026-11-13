"""Deployment upgrades are repeatable and errors stop API startup."""

import os
import subprocess

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.core.config import get_settings
from app.migrate import upgrade_database


def test_common_learning_migration_preserves_existing_questions(tmp_path, monkeypatch):
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
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert tuple(
                connection.execute(
                    text(
                        "SELECT word, correct_index, learned_at, ipa FROM common_word_questions"
                    )
                ).one()
            ) == ("hello", 0, None, None)
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
