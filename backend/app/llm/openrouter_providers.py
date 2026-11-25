"""Discover distinct provider routing slugs for the configured OpenRouter model."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.llm.openrouter_review import ReviewError


def model_providers(
    model: str, *, api_key: str, base_url: str, timeout: float
) -> list[str]:
    # Routing suffixes select a policy rather than a different model catalog entry.
    name, separator, suffix = model.rpartition(":")
    catalog_model = name if separator and suffix in {"nitro", "floor"} else model
    model_path = quote(catalog_model, safe="/:")
    request = Request(
        f"{base_url.rstrip('/')}/models/{model_path}/endpoints",
        headers={"Authorization": f"Bearer {api_key.strip()}"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(1048577)
        if len(raw) > 1048576:
            raise ValueError("Provider list too large")
        endpoints = json.loads(raw)["data"]["endpoints"]
        if not isinstance(endpoints, list):
            raise TypeError("Invalid provider list")
        providers: list[str] = []
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                continue
            tag = endpoint.get("tag")
            if not isinstance(tag, str):
                continue
            # Exclude regional/quantization variants of the same provider from retries.
            slug = tag.partition("/")[0].lower()
            if re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug) and slug not in providers:
                providers.append(slug)
        if not providers:
            raise ValueError("No providers")
        return providers[:3]
    except HTTPError as exc:
        raise ReviewError(
            "Provider discovery failed.",
            "provider_http",
            diagnostic=f"Provider discovery failed with HTTP {exc.code}.",
        ) from None
    except (URLError, OSError):
        raise ReviewError(
            "Provider discovery failed.",
            "provider_connection",
            diagnostic="Could not retrieve the model's provider list.",
        ) from None
    except (ValueError, KeyError, TypeError):
        raise ReviewError(
            "Provider discovery failed.",
            "invalid_response",
            diagnostic="The model's provider list is unavailable or invalid.",
        ) from None
