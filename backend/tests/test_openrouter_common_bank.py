"""Operator vocabulary generation uses structured output and the existing safe transport."""

import io
import json
from unittest.mock import patch

import pytest

from app.llm.openrouter_common_bank import generate_bank_words
from app.llm.openrouter_review import ReviewError

ENTRY = {
    "word": "reliable",
    "part_of_speech": "adjective",
    "english_explanation": "Able to be trusted.",
    "example_sentence": "She is a reliable colleague.",
    "ipa": "/rɪˈlaɪəbl/",
}


def response(words=None, finish="stop"):
    return io.BytesIO(
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": finish,
                        "message": {
                            "content": json.dumps(
                                {"words": [ENTRY] if words is None else words}
                            )
                        },
                    }
                ]
            }
        ).encode()
    )


def generate(count=1):
    return generate_bank_words(
        count,
        ["home", "work"],
        model="test/model",
        api_key="placeholder-test-key",
        timeout=30,
    )


def test_generates_word_content_with_count_exclusions_and_schema():
    with patch("app.llm.openrouter_common.urlopen", return_value=response()) as request:
        words = generate()
    assert words[0].word == "reliable"
    payload = json.loads(request.call_args.args[0].data)
    assert json.loads(payload["messages"][1]["content"]) == {
        "count": 1,
        "excluded_words": ["home", "work"],
    }
    assert payload["response_format"]["json_schema"]["name"] == "common_bank_words"
    assert (
        "questions"
        not in payload["response_format"]["json_schema"]["schema"]["properties"]
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"word": " "},
        {"word": "123"},
        {"english_explanation": " "},
        {"example_sentence": " "},
        {"part_of_speech": "unknown"},
        {"ipa": "not IPA"},
        {"extra": "unexpected"},
    ],
)
def test_invalid_words_are_rejected(changes):
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            return_value=response([{**ENTRY, **changes}]),
        ),
        pytest.raises(ReviewError),
    ):
        generate()


@pytest.mark.parametrize("words", [[], [ENTRY, ENTRY]])
def test_empty_or_excess_output_is_rejected(words):
    with (
        patch("app.llm.openrouter_common.urlopen", return_value=response(words)),
        pytest.raises(ReviewError),
    ):
        generate()


def test_truncated_content_is_rejected():
    with (
        patch(
            "app.llm.openrouter_common.urlopen", return_value=response(finish="length")
        ),
        pytest.raises(ReviewError),
    ):
        generate()
