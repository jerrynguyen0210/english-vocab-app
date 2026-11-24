"""Low effort and provider recovery retain deadlines, validation and retry bounds."""

import io
import itertools
import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app.llm.openrouter_common import request_common_json
from app.llm.openrouter_review import ReviewError, generate_review


def completed(finish="stop", content=None):
    return io.BytesIO(
        json.dumps(
            {
                "provider": "Groq",
                "choices": [
                    {
                        "finish_reason": finish,
                        "message": {
                            "content": (
                                json.dumps({"sentence": "She is a reliable colleague."})
                                if content is None
                                else content
                            )
                        },
                    }
                ],
            }
        ).encode()
    )


def rejection(code, message="private-provider-error"):
    return HTTPError(
        "https://example.test",
        code,
        "Rejected",
        {},
        io.BytesIO(json.dumps({"error": {"message": message}}).encode()),
    )


def invoke(kind, model="test/model"):
    options = {
        "api_key": "private-key",
        "base_url": "https://example.test",
        "timeout": 30,
    }
    if kind == "review":
        return generate_review("reliable", "private-meaning", model=model, **options)
    return request_common_json(
        {
            "model": model,
            "reasoning": {"enabled": False},
            "max_tokens": 4096,
            "stream": False,
            "response_format": {"type": "json_object"},
            "provider": {"require_parameters": True, "sort": "latency"},
            "messages": ["private-prompt"],
        },
        **options,
    )


@pytest.fixture(params=["review", "common"])
def kind(request):
    return request.param


def transport(kind):
    return f"app.llm.openrouter_{'review' if kind == 'review' else 'common'}.urlopen"


@pytest.mark.parametrize("model", ["openai/gpt-oss-20b", "openai/gpt-oss-120b:nitro"])
def test_known_models_start_with_low_effort(kind, model):
    with patch(transport(kind), return_value=completed()) as request:
        invoke(kind, model)
    request.assert_called_once()
    payload = json.loads(request.call_args.args[0].data)
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["max_tokens"] == (4096 if kind == "review" else 16000)


@pytest.mark.parametrize("code", [502, 503, 504])
def test_transient_http_failure_retries_once(kind, code):
    with patch(transport(kind), side_effect=[rejection(code), completed()]) as request:
        assert invoke(kind)
    assert request.call_count == 2
    first, second = request.call_args_list
    assert 0 < second.kwargs["timeout"] <= first.kwargs["timeout"] <= 30
    payload = json.loads(second.args[0].data)
    assert payload["provider"]["allow_fallbacks"] is True
    assert payload["response_format"]


def test_completion_error_excludes_known_failed_provider(kind):
    with patch(
        transport(kind), side_effect=[completed("error"), completed()]
    ) as request:
        assert invoke(kind)
    payload = json.loads(request.call_args.args[0].data)
    assert payload["provider"]["ignore"] == ["groq"]


@pytest.mark.parametrize("failure", ["http", "completion"])
def test_repeated_provider_failure_stops_after_one_retry(kind, failure):
    failures = (
        [rejection(502), rejection(502)]
        if failure == "http"
        else [
            completed("error"),
            completed("error"),
        ]
    )
    with (
        patch(transport(kind), side_effect=failures) as request,
        pytest.raises(ReviewError),
    ):
        invoke(kind)
    assert request.call_count == 2


def test_truncation_is_not_treated_as_transient_failure(kind):
    with (
        patch(transport(kind), return_value=completed("length")) as request,
        pytest.raises(ReviewError),
    ):
        invoke(kind)
    request.assert_called_once()


@pytest.mark.parametrize(
    "order", list(itertools.permutations(["reasoning", "schema", "provider"]))
)
def test_capability_fallbacks_and_provider_retry_work_in_any_order(kind, order):
    failures = {
        "reasoning": lambda: rejection(400, "Reasoning is mandatory"),
        "schema": lambda: rejection(400, "response_format is not supported"),
        "provider": lambda: rejection(502),
    }
    with patch(
        transport(kind),
        side_effect=[
            *(failures[name]() for name in order),
            completed(),
        ],
    ) as request:
        assert invoke(kind)
    assert request.call_count == 4
    payload = json.loads(request.call_args.args[0].data)
    assert payload["reasoning"] == {"effort": "low"}
    assert "response_format" not in payload
    timeouts = [call.kwargs["timeout"] for call in request.call_args_list]
    assert timeouts == sorted(timeouts, reverse=True)


def test_provider_retry_still_rejects_invalid_json(kind):
    with patch(
        transport(kind), side_effect=[completed("error"), completed(content="invalid")]
    ):
        if kind == "review":
            with pytest.raises(ReviewError):
                invoke(kind)
        else:
            # The Common transport returns content; its callers own JSON/schema validation.
            assert invoke(kind) == "invalid"


def test_retry_does_not_make_another_request_after_deadline(kind):
    module = "openrouter_review" if kind == "review" else "openrouter_common"
    with (
        patch(transport(kind), side_effect=rejection(502)) as request,
        patch(f"app.llm.{module}.time.monotonic", side_effect=[0, 1, 31]),
        pytest.raises(ReviewError),
    ):
        invoke(kind)
    request.assert_called_once()


def test_schema_fallback_preserves_failed_provider_exclusion(kind):
    with patch(
        transport(kind),
        side_effect=[
            completed("error"),
            rejection(400, "response_format is not supported"),
            completed(),
        ],
    ) as request:
        assert invoke(kind)
    payload = json.loads(request.call_args.args[0].data)
    assert payload["provider"]["ignore"] == ["groq"]
    assert payload["provider"]["allow_fallbacks"] is True
    assert "require_parameters" not in payload["provider"]
