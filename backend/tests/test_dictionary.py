from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi.testclient import TestClient

from app.api.dependencies import get_current_user
from app.core.database import get_session
from app.core.text import normalise_word
from app.main import app
from app.services.dictionary import search_dictionary

PARTS = ["noun", "verb", "adjective", "adverb"]
FORMS = ["V1", "V2", "V3"]


def test_create_family_and_shared_past_spelling():
    entries = search_dictionary("create", True, PARTS, FORMS)
    by_word = {entry.word: entry for entry in entries}
    assert {"create", "created", "creation", "creative", "creatively"} <= by_word.keys()
    assert by_word["created"].verb_forms == ["V2", "V3"]
    assert all(entry.english_explanation for entry in entries)
    assert "make" not in by_word


def test_filters_and_irregular_forms():
    entries = search_dictionary("write", True, ["verb"], ["V2", "V3"])
    assert {entry.word for entry in entries} == {"wrote", "written"}
    assert search_dictionary("create", True, ["verb"], []) == []
    assert all(
        entry.part_of_speech == "noun"
        for entry in search_dictionary("create", True, ["noun"], FORMS)
    )
    assert {
        entry.word for entry in search_dictionary("create", False, PARTS, FORMS)
    } == {"create"}


def test_unknown_and_inflected_query():
    assert search_dictionary("zzxxyyqq", True, PARTS, FORMS) == []
    assert {"written"} == {
        entry.word for entry in search_dictionary("written", False, ["verb"], FORMS)
    }


def test_exact_search_ignores_hidden_filters():
    for query in ("create", "created", "write", "wrote", "written", "creation"):
        entries = search_dictionary(query, False, [], [])
        assert entries
        assert {normalise_word(entry.word) for entry in entries} == {query}
    assert search_dictionary("zzxxyyqq", False, [], []) == []
    assert {
        entry.word for entry in search_dictionary(" WRITTEN ", False, [], [])
    } == {"written"}


def test_concurrent_search_and_cached_results_are_not_mutated():
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: search_dictionary("create", True, PARTS, FORMS), range(8)
            )
        )
    assert all(result == results[0] for result in results)
    search_dictionary("create", True, ["verb"], ["V2"])
    created = next(
        entry
        for entry in search_dictionary("create", True, ["verb"], FORMS)
        if entry.word == "created"
    )
    assert created.verb_forms == ["V2", "V3"]


def test_search_endpoint_validation_and_authentication(monkeypatch):
    with TestClient(app) as client:
        assert client.get("/api/v1/words/search?q=create").status_code == 401
        app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=None)
        app.dependency_overrides[get_session] = lambda: Mock(scalars=lambda _: [])
        try:
            response = client.get(
                "/api/v1/words/search",
                params=[("q", " WRITE "), ("parts", "verb"), ("forms", "V3")],
            )
            assert response.status_code == 200
            assert [entry["word"] for entry in response.json()] == ["written"]
            assert response.headers["Cache-Control"] == "no-store"
            exact = client.get(
                "/api/v1/words/search",
                params={
                    "q": " WRITTEN ",
                    "include_family": "false",
                    "parts": "noun",
                    "forms": "V1",
                },
            )
            assert exact.status_code == 200
            assert {entry["word"] for entry in exact.json()} == {"written"}
            for params in (
                {"q": " "},
                {"q": "x" * 201},
                {"q": "create", "parts": "invalid"},
                {"q": "create", "forms": "V4"},
            ):
                assert (
                    client.get("/api/v1/words/search", params=params).status_code == 422
                )

            def unavailable(*args):
                raise LookupError("missing corpus")

            monkeypatch.setattr("app.services.words.search_dictionary", unavailable)
            assert client.get("/api/v1/words/search?q=create").status_code == 503
        finally:
            app.dependency_overrides.clear()


def test_review_parts_and_family_use_dictionary_inflections():
    from app.services.dictionary import review_family, review_parts

    assert "verb" in review_parts("create")
    assert "verb" in review_parts("written")
    assert review_parts("zzxxyyqq") == frozenset()
    assert {"create", "created", "creative", "creation"} <= set(review_family("create"))


def test_review_lexicon_failure_preserves_general_fallback(monkeypatch):
    from app.services import dictionary

    def unavailable(*_):
        raise LookupError("missing corpus")

    dictionary.review_parts.cache_clear()
    monkeypatch.setattr(dictionary, "_lookup", unavailable)
    try:
        assert dictionary.review_parts("custom-test-word") == frozenset()
        assert dictionary.review_family("custom-test-word") == ()
    finally:
        dictionary.review_parts.cache_clear()
