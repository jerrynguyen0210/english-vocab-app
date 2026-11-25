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
