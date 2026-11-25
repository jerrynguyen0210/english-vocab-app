"""Provider discovery yields at most three different routing providers."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError

import pytest

from app.llm.openrouter_providers import model_providers
from app.llm.openrouter_review import ReviewError


def discover(model="test/model"):
    return model_providers(
        model,
        api_key="placeholder",
        base_url="https://example.test/api/v1",
        timeout=5,
    )


def test_deduplicates_provider_variants_and_limits_to_three():
    endpoints = [
        {"tag": tag}
        for tag in [
            "groq/turbo",
            "groq/default",
            "deepinfra/fp4",
            "coreweave/fp4",
            "venice/int4",
        ]
    ]
    with patch(
        "app.llm.openrouter_providers.urlopen",
        return_value=io.BytesIO(
            json.dumps({"data": {"endpoints": endpoints}}).encode()
        ),
    ):
        assert discover() == ["groq", "deepinfra", "coreweave"]


@pytest.mark.parametrize(
    "suffix, expected", [(":nitro", ""), (":free", ":free"), ("", "")]
)
def test_discovery_uses_configured_model_endpoint(suffix, expected):
    with patch(
        "app.llm.openrouter_providers.urlopen",
        return_value=io.BytesIO(b'{"data":{"endpoints":[{"tag":"groq"}]}}'),
    ) as request:
        assert discover("test/model" + suffix) == ["groq"]
    assert (
        request.call_args.args[0].full_url
        == f"https://example.test/api/v1/models/test/model{expected}/endpoints"
    )
    assert request.call_args.kwargs["timeout"] == 5


@pytest.mark.parametrize("body", [b"not JSON", b'{"data":{"endpoints":[]}}', b"{}"])
def test_invalid_catalog_is_reported_without_contents(body):
    with (
        patch("app.llm.openrouter_providers.urlopen", return_value=io.BytesIO(body)),
        pytest.raises(ReviewError) as failure,
    ):
        discover()
    assert (
        failure.value.diagnostic
        == "The model's provider list is unavailable or invalid."
    )


def test_discovery_http_error_is_sanitized():
    with (
        patch(
            "app.llm.openrouter_providers.urlopen",
            side_effect=HTTPError(
                "https://example.test",
                401,
                "private details",
                {},
                io.BytesIO(b"private"),
            ),
        ),
        pytest.raises(ReviewError) as failure,
    ):
        discover()
    assert failure.value.diagnostic == "Provider discovery failed with HTTP 401."


def capacity_discover(endpoints, **kwargs):
    with patch(
        "app.llm.openrouter_providers.urlopen",
        return_value=io.BytesIO(
            json.dumps({"data": {"endpoints": endpoints}}).encode()
        ),
    ):
        return model_providers(
            "test/model",
            api_key="placeholder",
            base_url="https://example.test",
            timeout=5,
            minimum_context=20000,
            minimum_output=16000,
            minimum_prompt=4000,
            **kwargs,
        )


def test_capacity_filters_endpoints_before_deduplication_and_pins_variant():
    endpoints = [
        {"tag": "groq/small", "context_length": 8000, "max_completion_tokens": 16000},
        {"tag": "other", "context_length": 32000, "max_completion_tokens": 4096},
        {
            "tag": "short-input",
            "context_length": 32000,
            "max_completion_tokens": 16000,
            "max_prompt_tokens": 1000,
        },
        {"tag": "unknown", "max_completion_tokens": 16000},
        {"tag": "groq/large", "context_length": 32000, "max_completion_tokens": 16000},
        {
            "tag": "groq/another",
            "context_length": 32000,
            "max_completion_tokens": 16000,
        },
        {"tag": "deepinfra", "context_length": 20000, "max_completion_tokens": None},
    ]
    assert capacity_discover(endpoints) == ["groq/large", "deepinfra"]


def test_insufficient_capacity_explains_how_to_retry():
    with pytest.raises(ReviewError) as failure:
        capacity_discover(
            [{"tag": "groq", "context_length": 8192, "max_completion_tokens": 4096}]
        )
    assert failure.value.category == "invalid_input"
    assert "Reduce batch size" in failure.value.diagnostic


def test_selected_providers_filter_before_limit_and_preserve_order():
    endpoints = [
        {"tag": tag, "context_length": 32000, "max_completion_tokens": 16000}
        for tag in ["first", "second", "third", "fourth/small", "fifth", "fourth/large"]
    ]
    assert capacity_discover(
        endpoints, selected_providers=["fifth", "fourth/large"]
    ) == ["fifth", "fourth/large"]


@pytest.mark.parametrize("selected", [["missing"], ["small"]])
def test_selected_providers_never_fall_back_to_unselected_endpoints(selected):
    with pytest.raises(ReviewError) as failure:
        capacity_discover(
            [
                {"tag": "small", "context_length": 8192},
                {"tag": "large", "context_length": 32000},
            ],
            selected_providers=selected,
        )
    assert failure.value.category == "invalid_input"
    assert "No selected provider" in failure.value.diagnostic
