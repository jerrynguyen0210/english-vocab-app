"""Operator generation persists exactly the requested number of unique SQL entries."""

from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.database import Base
from app.models import CommonWord
from app.schemas.common_word_bank import GeneratedBankWord
from app.services.common_word_bank import BankGenerationStopped, populate_bank


def word(value="hello"):
    return GeneratedBankWord(
        word=value,
        part_of_speech="noun",
        english_explanation="A test meaning.",
        example_sentence=f"We use {value} often.",
        ipa="/test/",
    )


@pytest.fixture
def bank(api_database_url):
    engine = create_engine(api_database_url)
    Base.metadata.create_all(engine)
    settings = Settings(
        _env_file=None,
        database_url=api_database_url,
        secret_key="placeholder-test-secret",
        openrouter_model="test/model",
        openrouter_api_key="placeholder-test-key",
    )
    yield engine, settings
    engine.dispose()


def total(engine):
    with engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(CommonWord))


def test_operator_count_of_1000_is_generated_in_small_batches_and_saved(
    bank, monkeypatch
):
    engine, settings = bank
    serial = 0
    requests = []

    def generate(count, excluded, **kwargs):
        nonlocal serial
        requests.append((count, len(excluded)))
        words = []
        for _ in range(count):
            # Synthetic provider output, never production vocabulary.
            letters = (
                chr(97 + serial // 676)
                + chr(97 + serial // 26 % 26)
                + chr(97 + serial % 26)
            )
            words.append(word("term " + letters))
            serial += 1
        return words

    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    progress = Mock()
    assert populate_bank(engine, 1000, settings, progress=progress) == 1000
    assert total(engine) == 1000
    assert len(requests) == 50 and all(size == 20 for size, _ in requests)
    assert requests[-1][1] == 980
    progress.assert_called_with(1000, 1000)


def test_normalized_duplicates_are_skipped_and_remaining_count_is_filled(
    bank, monkeypatch
):
    engine, settings = bank
    responses = [[word("Hello"), word("HELLO"), word("world")], [word("home")]]
    calls = []

    def generate(count, excluded, **kwargs):
        calls.append((count, excluded))
        return responses.pop(0)

    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    assert populate_bank(engine, 3, settings) == 3
    assert calls == [(3, []), (1, ["hello", "world"])]
    with Session(engine) as db:
        assert {w.normalised_word for w in db.scalars(select(CommonWord))} == {
            "hello",
            "world",
            "home",
        }


def test_exclusions_include_existing_bank_and_every_completed_batch(bank, monkeypatch):
    engine, settings = bank
    with engine.begin() as connection:
        connection.execute(
            CommonWord.__table__.insert().values(
                word="Hello",
                normalised_word="hello",
                part_of_speech="noun",
                english_explanation="Existing meaning",
            )
        )
    new_words = ["home", "work", "travel", "shop", "friend", "garden"]
    calls = []

    def generate(count, excluded, **kwargs):
        index = len(calls)
        assert count == 1
        assert excluded == sorted(["hello", *new_words[:index]])
        calls.append(excluded)
        return [word(new_words[index])]

    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    assert populate_bank(engine, 6, settings, batch_size=1) == 6
    assert len(calls) == 6
    assert total(engine) == 7


def test_duplicates_inserted_by_another_operator_are_not_counted(bank, monkeypatch):
    engine, settings = bank
    calls = 0

    def generate(count, excluded, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            with engine.begin() as connection:
                connection.execute(
                    CommonWord.__table__.insert().values(
                        word="hello",
                        normalised_word="hello",
                        part_of_speech="noun",
                        english_explanation="Existing meaning",
                    )
                )
            return [word("hello"), word("world")]
        assert count == 1
        return [word("home")]

    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    assert populate_bank(engine, 2, settings) == 2
    assert total(engine) == 3


def test_stalled_duplicate_generation_stops_and_keeps_committed_batches(
    bank, monkeypatch
):
    engine, settings = bank
    calls = 0

    def generate(*args, **kwargs):
        nonlocal calls
        calls += 1
        return [word("hello")]

    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    with pytest.raises(BankGenerationStopped) as failure:
        populate_bank(engine, 2, settings, batch_size=1)
    assert failure.value.inserted == 1
    assert failure.value.requested == 2
    assert calls == 4 and total(engine) == 1


def test_provider_failure_reports_remaining_count_without_rolling_back_completed_batches(
    bank, monkeypatch
):
    from app.llm.openrouter_review import ReviewError

    engine, settings = bank
    responses = iter([[word("hello")], ReviewError("Private provider response")])

    def generate(*args, **kwargs):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    with pytest.raises(BankGenerationStopped) as failure:
        populate_bank(engine, 2, settings, batch_size=1)
    assert total(engine) == 1 and failure.value.inserted == 1
    assert "Private provider response" not in str(failure.value)


def test_invalid_batch_does_not_insert_any_content(bank, monkeypatch):
    engine, settings = bank
    monkeypatch.setattr(
        "app.services.common_word_bank.generate_bank_words",
        lambda *args, **kwargs: [word("hello"), word("world")],
    )
    with pytest.raises(BankGenerationStopped):
        populate_bank(engine, 1, settings)
    assert total(engine) == 0


def test_provider_diagnostic_reaches_operator_and_keeps_completed_batches(
    bank, monkeypatch
):
    from app.llm.openrouter_review import ReviewError

    engine, settings = bank
    generate = Mock(
        side_effect=[
            [word("hello")],
            ReviewError(
                "Private provider response",
                "provider_http",
                diagnostic="Provider request failed with HTTP 429.",
            ),
        ]
    )
    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    with pytest.raises(BankGenerationStopped) as failure:
        populate_bank(engine, 2, settings, batch_size=1)
    assert "HTTP 429" in str(failure.value)
    assert "Private provider response" not in str(failure.value)
    assert "Saved 1 of 2" in str(failure.value)
    assert total(engine) == 1


@pytest.mark.parametrize("count", [0, -1, True])
def test_invalid_count_never_calls_llm(bank, monkeypatch, count):
    engine, settings = bank
    generate = Mock()
    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    with pytest.raises(ValueError):
        populate_bank(engine, count, settings)
    generate.assert_not_called()


def test_missing_key_never_calls_llm(bank, monkeypatch):
    engine, settings = bank
    settings.openrouter_api_key = type(settings.openrouter_api_key)("")
    generate = Mock()
    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    with pytest.raises(ValueError):
        populate_bank(engine, 1, settings)
    generate.assert_not_called()


@pytest.mark.parametrize("interactive", [False, True])
def test_cli_accepts_operator_count_and_saves_to_sql(
    bank, monkeypatch, capsys, interactive
):
    from app import generate_common_words as cli

    engine, settings = bank
    monkeypatch.setattr(cli, "get_engine", lambda: engine)
    monkeypatch.setattr(cli, "get_settings", lambda: settings)
    monkeypatch.setattr("builtins.input", lambda prompt: "2")
    monkeypatch.setattr(
        "sys.argv",
        ["generate_common_words"] + ([] if interactive else ["--count", "2"]),
    )
    monkeypatch.setattr(
        "app.services.common_word_bank.generate_bank_words",
        lambda *args, **kwargs: [word("hello"), word("world")],
    )
    cli.main()
    assert total(engine) == 2
    assert "Saved 2/2" in capsys.readouterr().out


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "hello"])
def test_cli_rejects_invalid_operator_input_before_accessing_database(
    monkeypatch, value
):
    from app import generate_common_words as cli

    engine = Mock()
    monkeypatch.setattr(cli, "get_engine", engine)
    monkeypatch.setattr("sys.argv", ["generate_common_words", "--count", value])
    with pytest.raises(SystemExit) as failure:
        cli.main()
    assert failure.value.code == 2
    engine.assert_not_called()


def test_fifty_word_batches_are_saved_and_fifty_one_is_rejected(bank, monkeypatch):
    engine, settings = bank
    generated = [
        word("term " + chr(97 + i // 26) + chr(97 + i % 26)) for i in range(50)
    ]
    generate = Mock(return_value=generated)
    monkeypatch.setattr("app.services.common_word_bank.generate_bank_words", generate)
    assert populate_bank(engine, 50, settings, batch_size=50) == 50
    assert generate.call_args.args[0] == 50
    with pytest.raises(ValueError):
        populate_bank(engine, 51, settings, batch_size=51)
    assert total(engine) == 50
