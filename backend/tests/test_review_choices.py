import pytest
from pydantic import ValidationError

import app.services.review_choices as choices
from app.api import SessionItem
from app.models.word import normalise_word


def profiles(**words):
    return {word: frozenset(parts) for word, parts in words.items()}


def assert_options(options, target):
    assert len(options) == 4
    keys = [normalise_word(word) for word in options]
    assert len(set(keys)) == 4
    assert keys.count(normalise_word(target)) == 1


def test_similar_pos_saved_words_take_priority(monkeypatch):
    def unexpected(_):
        raise AssertionError("Family must not be needed")

    monkeypatch.setattr(choices, "review_family", unexpected)
    options = choices.review_options(
        "garden",
        profiles(
            garden=["noun"],
            journey=["noun"],
            memory=["noun"],
            shelter=["noun"],
            discover=["verb"],
        ),
    )
    assert_options(options, "garden")
    assert set(options) == {"garden", "journey", "memory", "shelter"}


def test_family_precedes_other_saved_words(monkeypatch):
    monkeypatch.setattr(
        choices,
        "review_family",
        lambda _: ("create", "created", "creating", "creative"),
    )
    options = choices.review_options(
        "create",
        profiles(create=["verb"], build=["verb"], garden=["noun"], journey=["noun"]),
    )
    assert_options(options, "create")
    assert "build" in options
    assert len(set(options) & {"created", "creating", "creative"}) == 2
    assert "garden" not in options and "journey" not in options


def test_other_saved_words_precede_dictionary_and_deduplicate(monkeypatch):
    monkeypatch.setattr(
        choices, "review_family", lambda _: (" ＣＲＥＡＴＥ ", "CREATED", "created", "")
    )
    options = choices.review_options(
        "create", profiles(create=["verb"], garden=["noun"], journey=["noun"])
    )
    assert_options(options, "create")
    assert {normalise_word(word) for word in options} == {
        "create",
        "created",
        "garden",
        "journey",
    }


@pytest.mark.parametrize(
    "target", ["unknown-custom-word", "journey", "discover", "ＣＡＲＥＦＵＬ"]
)
def test_dictionary_fallback_guarantees_four_for_empty_bank(monkeypatch, target):
    monkeypatch.setattr(choices, "review_family", lambda _: ())
    monkeypatch.setattr(choices, "review_parts", lambda _: frozenset())
    options = choices.review_options(target, {})
    assert_options(options, target)
    assert set(options) - {target} <= {
        word for words in choices.GENERAL_VOCABULARY.values() for word in words
    }


@pytest.mark.parametrize(
    "options",
    [
        [],
        ["one"],
        ["one", "two", "three"],
        ["one", "two", "three", "four", "five"],
        ["one", "ＯＮＥ", "three", "four"],
        ["one", "", "three", "four"],
    ],
)
def test_session_contract_rejects_invalid_options(options):
    with pytest.raises(ValidationError):
        SessionItem.model_validate(
            {
                "word_id": "11111111-1111-1111-1111-111111111111",
                "attempt_id": "22222222-2222-2222-2222-222222222222",
                "prompt_sentence": "_____",
                "english_explanation": "Meaning",
                "review_token": "test",
                "choices": options,
            }
        )
