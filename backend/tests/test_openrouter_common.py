"""Provider requests stay offline and malformed LLM output never enters the bank."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.llm.openrouter_common import SYSTEM_PROMPT, generate_common_words
from app.llm.openrouter_review import ReviewError


def candidate(**overrides):
    return dict(
        word="reliable",
        part_of_speech="adjective",
        explanation="Able to be trusted.",
        example="She is a reliable colleague.",
        choices=[
            "Easy to forget",
            "Able to be trusted",
            "Very expensive",
            "Difficult to use",
        ],
        correct_index=1,
        **overrides,
    )


def envelope(words, finish_reason="stop"):
    return io.BytesIO(
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": finish_reason,
                        "message": {"content": json.dumps({"words": words})},
                    }
                ]
            }
        ).encode()
    )


def generate():
    return generate_common_words(
        ["eager"], model="test/model", api_key="placeholder-test-key"
    )


def test_requests_native_everyday_words_and_four_unambiguous_meanings():
    with patch(
        "app.llm.openrouter_common.urlopen", return_value=envelope([candidate()])
    ) as request:
        items = generate()
    assert items[0].word == "reliable" and items[0].correct_index == 1
    payload = json.loads(request.call_args.args[0].data)
    assert "native English speakers" in SYSTEM_PROMPT
    assert "everyday conversation" in SYSTEM_PROMPT
    assert "Exactly one meaning" in SYSTEM_PROMPT
    assert json.loads(payload["messages"][1]["content"])["excluded_words"] == ["eager"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["max_tokens"] >= 4000


def test_prompt_includes_all_learned_and_saved_exclusions_without_truncation():
    learned = [f"learned{i}" for i in range(600)]
    excluded = [f"saved{i}" for i in range(600)]
    with patch(
        "app.llm.openrouter_common.urlopen", return_value=envelope([candidate()])
    ) as request:
        generate_common_words(
            excluded,
            learned_words=learned,
            model="test/model",
            api_key="placeholder-test-key",
        )
    payload = json.loads(request.call_args.args[0].data)
    content = json.loads(payload["messages"][1]["content"])
    assert content["learned_words"] == learned
    assert content["excluded_words"] == excluded
    assert "Do not include any learned word" in SYSTEM_PROMPT


@pytest.mark.parametrize(
    "change",
    [
        {"choices": ["One", "Two", "Three"]},
        {"choices": ["One", "Two", "Three", " one "]},
        {"choices": ["One", "Two", "Three", "   "]},
        {"choices": ["One", "Two", "Three", 4]},
        {"correct_index": 4},
        {"correct_index": True},
        {"word": "not a word"},
        {"example": "She is a colleague."},
        {"explanation": " "},
        {"part_of_speech": "unknown"},
        {"unexpected": "field"},
    ],
)
def test_rejects_invalid_model_questions(change):
    item = candidate()
    item.update(change)
    with (
        patch("app.llm.openrouter_common.urlopen", return_value=envelope([item])),
        pytest.raises(ReviewError) as error,
    ):
        generate()
    assert error.value.category == "invalid_response"


@pytest.mark.parametrize("raw", [b"not json", b"{}", b'{"choices":[]}', b"x" * 262145])
def test_rejects_bad_envelopes_and_oversized_response(raw):
    with (
        patch("app.llm.openrouter_common.urlopen", return_value=io.BytesIO(raw)),
        pytest.raises(ReviewError),
    ):
        generate()


def test_rejects_truncated_generation():
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            return_value=envelope([candidate()], "length"),
        ),
        pytest.raises(ReviewError),
    ):
        generate()


def test_falls_back_for_schema_unsupported_model_but_keeps_validation():
    error = HTTPError(
        "https://example.test",
        400,
        "Bad Request",
        {},
        io.BytesIO(b'{"error":{"message":"response_format not supported"}}'),
    )
    with patch(
        "app.llm.openrouter_common.urlopen",
        side_effect=[error, envelope([candidate()])],
    ) as request:
        assert len(generate()) == 1
    assert "response_format" not in json.loads(request.call_args.args[0].data)


@pytest.mark.parametrize(
    "failure",
    [
        URLError("private error"),
        HTTPError("https://example.test", 401, "private error", {}, None),
    ],
)
def test_provider_errors_do_not_expose_response_details(failure):
    with (
        patch("app.llm.openrouter_common.urlopen", side_effect=failure),
        pytest.raises(ReviewError) as error,
    ):
        generate()
    assert "private error" not in str(error.value)


def test_missing_key_does_not_contact_provider():
    with (
        patch("app.llm.openrouter_common.urlopen") as request,
        pytest.raises(ReviewError),
    ):
        generate_common_words([], model="test/model", api_key="")
    request.assert_not_called()
