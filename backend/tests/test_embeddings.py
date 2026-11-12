"""Embedding provider contract and vector validation stay offline."""

import io
import json
from urllib.error import URLError

import numpy as np
import pytest

from app.services import embeddings
from app.services.errors import TopicSearchUnavailable


@pytest.mark.parametrize(
    "vectors",
    [
        None,
        [],
        [[]],
        [[0, 0]],
        [[float("nan"), 1]],
        [[float("inf"), 0]],
        [[1, 0], [1]],
        [["bad", 0]],
        [1, 2],
    ],
)
def test_invalid_vectors_fail_without_becoming_no_matches(vectors):
    with pytest.raises(TopicSearchUnavailable):
        embeddings.normalized_vectors(vectors, 1)


def test_provider_contract_normalizes_batch(monkeypatch):
    settings = embeddings.get_settings()
    monkeypatch.setattr(settings, "ollama_url", "http://ollama.test:11434")
    monkeypatch.setattr(settings, "openrouter_url", "https://openrouter.test/api/v1")
    def request(req, *, timeout):
        assert req.full_url == "http://ollama.test:11434/api/embed"
        assert req.get_header("Authorization") is None
        payload = json.loads(req.data)
        assert payload["input"] == ["work", "hello"]
        assert payload["model"] == "embeddinggemma"
        assert timeout == 10
        return io.BytesIO(json.dumps({"embeddings": [[3, 4], [0, 2]]}).encode())

    monkeypatch.setattr(embeddings, "urlopen", request)
    result = embeddings.embed_texts(["work", "hello"])
    np.testing.assert_allclose(result, [[0.6, 0.8], [0, 1]])


@pytest.mark.parametrize(
    "response", [b"invalid json", b"[]", b"{}", b'{"embeddings": [[1, 0], [0, 1]]}']
)
def test_invalid_provider_response(response, monkeypatch):
    monkeypatch.setattr(embeddings, "urlopen", lambda *a, **kw: io.BytesIO(response))
    with pytest.raises(TopicSearchUnavailable):
        embeddings.embed_texts(["work"])


def test_provider_outage_is_sanitized(monkeypatch):
    def fail(*a, **kw):
        raise URLError("private provider body")

    monkeypatch.setattr(embeddings, "urlopen", fail)
    with pytest.raises(TopicSearchUnavailable) as caught:
        embeddings.embed_texts(["private topic"])
    assert "private" not in str(caught.value)
