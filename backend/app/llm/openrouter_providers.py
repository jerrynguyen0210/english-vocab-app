"""Discover distinct provider routing slugs for the configured OpenRouter model."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from app.llm.openrouter_review import ReviewError


def model_providers(
    model: str,
    *,
    api_key: str,
    base_url: str,
    timeout: float,
    minimum_context: int = 0,
    minimum_output: int = 0,
    minimum_prompt: int = 0,
    selected_providers: list[str] | None = None,
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
        if selected_providers:
            # Filter before capacity checks and the three-provider retry limit.
            endpoints = [
                endpoint
                for selected in selected_providers
                for endpoint in endpoints
                if isinstance(endpoint, dict)
                and isinstance(endpoint.get("tag"), str)
                and (
                    endpoint["tag"].casefold() == selected.casefold()
                    or endpoint["tag"].partition("/")[0].casefold()
                    == selected.casefold()
                )
            ]
        providers: list[str] = []
        seen: set[str] = set()
        for endpoint in endpoints:
            if not isinstance(endpoint, dict):
                continue
            if minimum_context or minimum_output or minimum_prompt:
                context = endpoint.get("context_length")
                output = endpoint.get("max_completion_tokens")
                prompt = endpoint.get("max_prompt_tokens")
                if (
                    type(context) is not int
                    or context < minimum_context
                    or (
                        output is not None
                        and (type(output) is not int or output < minimum_output)
                    )
                    or (
                        prompt is not None
                        and (type(prompt) is not int or prompt < minimum_prompt)
                    )
                ):
                    continue
            tag = endpoint.get("tag")
            if not isinstance(tag, str):
                continue
            # Exclude regional/quantization variants of the same provider from retries.
            slug = tag.partition("/")[0].lower()
            if re.fullmatch(r"[a-z0-9][a-z0-9-]*", slug) and slug not in seen:
                seen.add(slug)
                # Pin the checked endpoint variant when capacity was requested.
                providers.append(tag if minimum_context or minimum_output else slug)
        if not providers:
            if selected_providers:
                raise ReviewError(
                    "Selected providers are unavailable.",
                    "invalid_input",
                    diagnostic=(
                        "No selected provider has a compatible endpoint for this model and batch. "
                        "Check provider slugs, choose another model or reduce batch size."
                    ),
                )
            if minimum_context or minimum_output:
                raise ReviewError(
                    "No provider has sufficient verified capacity.",
                    "invalid_input",
                    diagnostic=(
                        f"No endpoint has verified context capacity for {minimum_context} tokens "
                        f"and output capacity for {minimum_output} tokens. "
                        "Reduce batch size or choose a model with larger limits."
                    ),
                )
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
