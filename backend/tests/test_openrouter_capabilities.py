"""Review generation adapts to mandatory reasoning without looping."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app.llm import openrouter_review
from app.llm.openrouter_review import ReviewError


def rejection(kind):
    message = {
        "reasoning": "Reasoning is mandatory for this endpoint and cannot be disabled.",
        "schema": "response_format json_schema is not supported.",
    }[kind]
    return HTTPError(
        "https://example.test",
        400,
        "Rejected",
        {},
        io.BytesIO(json.dumps({"error": {"message": message}}).encode()),
    )


def completed():
    output = {"sentence": "She is a reliable colleague."}
    return io.BytesIO(
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": json.dumps(output)},
                    }
                ]
            }
        ).encode()
    )


def generate():
    options = {"model": "test/model", "api_key": "placeholder-test-key"}
    return openrouter_review.generate_review(
        "reliable", "Able to be trusted", **options
    )


@pytest.mark.parametrize(
    "capabilities", [["reasoning"], ["reasoning", "schema"], ["schema", "reasoning"]]
)
def test_independent_capability_fallbacks_are_bounded_and_preserve_validation(
    capabilities,
):
    with patch(
        "app.llm.openrouter_review.urlopen",
        side_effect=[
            *(rejection(capability) for capability in capabilities),
            completed(),
        ],
    ) as request:
        assert generate()
    payloads = [json.loads(call.args[0].data) for call in request.call_args_list]
    assert payloads[0]["reasoning"] == {"enabled": False}
    assert request.call_count == len(capabilities) + 1
    final = payloads[-1]
    assert final["reasoning"] == {"effort": "low"}
    assert final["max_tokens"] == 4096
    if "schema" in capabilities:
        assert "response_format" not in final
    else:
        assert "response_format" in final


def test_repeated_mandatory_reasoning_rejection_does_not_loop():
    with (
        patch(
            "app.llm.openrouter_review.urlopen",
            side_effect=[rejection("reasoning"), rejection("reasoning")],
        ) as request,
        pytest.raises(ReviewError),
    ):
        generate()
    assert request.call_count == 2


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_auth_quota_and_server_errors_are_not_capability_retries(status):
    failure = HTTPError(
        "https://example.test",
        status,
        "Rejected",
        {},
        io.BytesIO(b'{"error":{"message":"Reasoning is mandatory"}}'),
    )
    with (
        patch("app.llm.openrouter_review.urlopen", side_effect=failure) as request,
        pytest.raises(ReviewError),
    ):
        generate()
    assert request.call_count == 1
