"""Operator vocabulary generation uses structured output and the existing safe transport."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

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


@pytest.fixture(autouse=True)
def providers(monkeypatch):
    available = ["groq"]
    monkeypatch.setattr(
        "app.llm.openrouter_common_bank.model_providers",
        lambda *args, **kwargs: available,
    )
    return available


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
        pytest.raises(ReviewError) as failure,
    ):
        generate()
    assert "output token limit" in failure.value.diagnostic


@pytest.mark.parametrize("status", [401, 402, 429, 503])
def test_http_failure_reports_status_without_provider_body(status):
    error = HTTPError(
        "https://example.test",
        status,
        "Rejected",
        {},
        io.BytesIO(b'{"error":{"message":"private provider details"}}'),
    )
    with (
        patch("app.llm.openrouter_common.urlopen", side_effect=error),
        pytest.raises(ReviewError) as failure,
    ):
        generate()
    assert failure.value.diagnostic.startswith(
        f"Provider request failed with HTTP {status}."
    )


def test_validation_failure_reports_field_without_generated_content():
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            return_value=response([{**ENTRY, "ipa": "private invalid IPA"}]),
        ),
        pytest.raises(ReviewError) as failure,
    ):
        generate()
    assert failure.value.diagnostic.startswith(
        "Generated vocabulary failed validation: ipa."
    )


def test_timeout_has_a_distinct_diagnostic():
    with (
        patch("app.llm.openrouter_common.urlopen", side_effect=TimeoutError()),
        pytest.raises(ReviewError) as failure,
    ):
        generate()
    assert failure.value.diagnostic.startswith("The provider request timed out.")


def routed_providers(request):
    payloads = [json.loads(call.args[0].data) for call in request.call_args_list]
    for payload in payloads:
        assert payload["provider"]["allow_fallbacks"] is False
        assert payload["model"] == "test/model"
        assert json.loads(payload["messages"][1]["content"])["excluded_words"] == [
            "home",
            "work",
        ]
    return [payload["provider"]["only"] for payload in payloads]


def test_invalid_text_and_invalid_word_data_retry_three_different_providers(providers):
    providers[:] = ["groq", "deepinfra", "coreweave"]
    invalid_json = io.BytesIO(
        json.dumps(
            {"choices": [{"finish_reason": "stop", "message": {"content": "not JSON"}}]}
        ).encode()
    )
    with patch(
        "app.llm.openrouter_common.urlopen",
        side_effect=[invalid_json, response([{**ENTRY, "ipa": "invalid"}]), response()],
    ) as request:
        assert generate()[0].word == "reliable"
    assert routed_providers(request) == [["groq"], ["deepinfra"], ["coreweave"]]


@pytest.mark.parametrize(
    "failure_kind", ["truncated", "http", "connection", "envelope"]
)
def test_provider_failures_switch_to_next_provider(providers, failure_kind):
    providers[:] = ["groq", "deepinfra", "coreweave"]
    failure = {
        "truncated": response(finish="length"),
        "http": HTTPError(
            "https://example.test", 503, "Unavailable", {}, io.BytesIO(b"{}")
        ),
        "connection": TimeoutError(),
        "envelope": io.BytesIO(b"not JSON"),
    }[failure_kind]
    with patch(
        "app.llm.openrouter_common.urlopen", side_effect=[failure, response()]
    ) as request:
        assert generate()[0].word == "reliable"
    assert routed_providers(request) == [["groq"], ["deepinfra"]]


def test_stops_after_three_failed_providers(providers):
    providers[:] = ["groq", "deepinfra", "coreweave"]
    with (
        patch(
            "app.llm.openrouter_common.urlopen", side_effect=TimeoutError()
        ) as request,
        pytest.raises(ReviewError) as failure,
    ):
        generate()
    assert routed_providers(request) == [["groq"], ["deepinfra"], ["coreweave"]]
    assert "Tried 3 distinct provider(s)" in failure.value.diagnostic


def test_schema_fallback_stays_on_selected_provider(providers):
    providers[:] = ["groq", "deepinfra", "coreweave"]
    rejection = HTTPError(
        "https://example.test",
        400,
        "Rejected",
        {},
        io.BytesIO(b'{"error":{"message":"json_schema not supported"}}'),
    )
    with patch(
        "app.llm.openrouter_common.urlopen", side_effect=[rejection, response()]
    ) as request:
        assert generate()[0].word == "reliable"
    assert routed_providers(request) == [["groq"], ["groq"]]
    assert "response_format" not in json.loads(request.call_args.args[0].data)


def test_provider_timeouts_share_one_batch_budget(providers):
    providers[:] = ["groq", "deepinfra", "coreweave"]
    with (
        patch(
            "app.llm.openrouter_common_bank.time.monotonic", side_effect=[0, 3, 12, 21]
        ),
        patch(
            "app.llm.openrouter_common_bank.request_common_json",
            side_effect=ReviewError("Timed out", "provider_connection"),
        ) as request,
        pytest.raises(ReviewError),
    ):
        generate()
    assert [call.kwargs["timeout"] for call in request.call_args_list] == [9, 9, 9]


def test_exhausted_deadline_does_not_start_another_request():
    with (
        patch("app.llm.openrouter_common_bank.time.monotonic", side_effect=[0, 30]),
        patch("app.llm.openrouter_common_bank.request_common_json") as request,
        pytest.raises(ReviewError) as failure,
    ):
        generate()
    request.assert_not_called()
    assert failure.value.diagnostic == "The provider fallback deadline was exhausted."
