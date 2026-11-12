"""Offline tests for OpenRouter prompt generation and response validation."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

import pytest

from app.llm.openrouter_review import OPENROUTER_URL, ReviewError, generate_review


class ReviewTests(unittest.TestCase):
    def response(self, sentence: str) -> io.BytesIO:
        return io.BytesIO(
            json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "stop",
                            "message": {"content": json.dumps({"sentence": sentence})},
                        }
                    ]
                }
            ).encode()
        )

    def test_request_and_masked_output(self) -> None:
        with patch(
            "app.llm.openrouter_review.urlopen",
            return_value=self.response(
                "She was reluctant to leave her friends behind."
            ),
        ) as call:
            result = generate_review(
                "reluctant", "unwilling", model="test/model", api_key="test-key"
            )
        self.assertEqual(
            result,
            {
                "prompt_sentence": "She was _____ to leave her friends behind.",
                "answer": "reluctant",
            },
        )
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, f"{OPENROUTER_URL}/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "test/model")
        self.assertEqual(
            payload["response_format"]["json_schema"]["schema"]["required"],
            ["sentence"],
        )

    def test_removes_bold_markers_around_answer(self) -> None:
        with patch(
            "app.llm.openrouter_review.urlopen",
            return_value=self.response("He was **ready** to take us home."),
        ):
            result = generate_review(
                "ready", "prepared", model="test/model", api_key="test-key"
            )
        self.assertEqual(result["prompt_sentence"], "He was _____ to take us home.")

    def test_rejects_missing_repeated_or_embedded_answer(self) -> None:
        for sentence in ("She left early.", "Go go home.", "The mango is ripe."):
            with (
                self.subTest(sentence=sentence),
                patch(
                    "app.llm.openrouter_review.urlopen",
                    return_value=self.response(sentence),
                ),
                self.assertRaises(ReviewError) as caught,
            ):
                generate_review("go", "move", model="test/model", api_key="test-key")
            self.assertEqual(caught.exception.category, "invalid_response")

    def test_phrase_and_unicode(self) -> None:
        with patch(
            "app.llm.openrouter_review.urlopen",
            return_value=self.response("Please TAKE   OFF your coat."),
        ):
            self.assertEqual(
                generate_review(
                    "take off", "remove", model="test/model", api_key="test-key"
                )["prompt_sentence"],
                "Please _____ your coat.",
            )

    def test_invalid_response(self) -> None:
        for content in (b"not json", b"{}", b'{"done": true, "response": "[]"}'):
            with (
                patch(
                    "app.llm.openrouter_review.urlopen",
                    return_value=io.BytesIO(content),
                ),
                self.assertRaises(ReviewError),
            ):
                generate_review("go", "move", model="test/model", api_key="test-key")

    def test_missing_api_key_does_not_call_provider(self) -> None:
        with (
            patch("app.llm.openrouter_review.urlopen") as call,
            self.assertRaisesRegex(ReviewError, "OPENROUTER_API_KEY") as caught,
        ):
            generate_review("go", "move", model="test/model", api_key="  ")
        call.assert_not_called()
        self.assertEqual(caught.exception.category, "invalid_input")

    def test_provider_errors_and_incomplete_responses(self) -> None:
        envelopes = [
            {"choices": []},
            {"error": {"message": "private provider error"}},
            {
                "choices": [
                    {
                        "finish_reason": "length",
                        "message": {"content": '{"sentence":"Go home."}'},
                    }
                ]
            },
            {"choices": [{"finish_reason": "stop", "message": {"content": None}}]},
        ]
        for envelope in envelopes:
            with (
                self.subTest(envelope=envelope),
                patch(
                    "app.llm.openrouter_review.urlopen",
                    return_value=io.BytesIO(json.dumps(envelope).encode()),
                ),
                self.assertRaises(ReviewError) as caught,
            ):
                generate_review("go", "move", model="test/model", api_key="test-key")
            self.assertEqual(caught.exception.category, "invalid_response")
            self.assertNotIn("private provider error", str(caught.exception))

    def test_http_errors(self) -> None:
        for code in (401, 402, 429, 500):
            with (
                self.subTest(code=code),
                patch(
                    "app.llm.openrouter_review.urlopen",
                    side_effect=HTTPError(
                        OPENROUTER_URL, code, "private response", {}, None
                    ),
                ),
                self.assertRaises(ReviewError) as caught,
            ):
                generate_review("go", "move", model="test/model", api_key="test-key")
            self.assertEqual(caught.exception.category, "provider_http")
            self.assertNotIn("private response", str(caught.exception))
            self.assertNotIn("test-key", str(caught.exception))

    def test_connection_failure(self) -> None:
        with (
            patch("app.llm.openrouter_review.urlopen", side_effect=URLError("refused")),
            self.assertRaisesRegex(ReviewError, "Cannot reach OpenRouter") as caught,
        ):
            generate_review("go", "move", model="test/model", api_key="test-key")
        self.assertEqual(caught.exception.category, "provider_connection")


if __name__ == "__main__":
    unittest.main()


@pytest.mark.parametrize("shell_key", [None, "shell-test-key"])
def test_cli_loads_backend_env_from_any_directory(
    tmp_path, monkeypatch, capsys, shell_key
):
    from app.llm import openrouter_review

    backend = tmp_path / "backend"
    script = backend / "app" / "llm" / "openrouter_review.py"
    script.parent.mkdir(parents=True)
    (backend / ".env").write_text(
        'OPENROUTER_API_KEY="file-test-key"\n'
        "OPENROUTER_MODEL=test/model\n"
        "OPENROUTER_URL=https://router.test/api/v1\n"
        "OPENROUTER_TIMEOUT_SECONDS=45\n"
    )
    for name in (
        "OPENROUTER_API_KEY",
        "OPENROUTER_MODEL",
        "OPENROUTER_URL",
        "OPENROUTER_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    if shell_key:
        monkeypatch.setenv("OPENROUTER_API_KEY", shell_key)
    monkeypatch.setattr(openrouter_review, "__file__", str(script))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv", [str(script), "--word", "reluctant", "--meaning", "unwilling"]
    )
    with (
        patch.dict("os.environ"),
        patch.object(
            openrouter_review,
            "generate_review",
            return_value={"prompt_sentence": "She was _____.", "answer": "reluctant"},
        ) as generate,
    ):
        assert openrouter_review.main() == 0
    generate.assert_called_once_with(
        "reluctant",
        "unwilling",
        model="test/model",
        api_key=shell_key or "file-test-key",
        base_url="https://router.test/api/v1",
        timeout=45,
    )
    output = capsys.readouterr().out
    assert "She was _____." in output
    assert "test-key" not in output


@pytest.mark.parametrize("status", [400, 404])
def test_schema_rejection_retries_without_schema(status):
    from app.llm import openrouter_review

    error = HTTPError(
        OPENROUTER_URL,
        status,
        "Bad request",
        {},
        io.BytesIO(
            json.dumps(
                {
                    "error": {
                        "message": "No endpoints found that can handle the requested parameters"
                    }
                }
            ).encode()
        ),
    )
    response = ReviewTests().response("She was reluctant to leave.")
    with patch.object(
        openrouter_review, "urlopen", side_effect=[error, response]
    ) as call:
        result = generate_review(
            "reluctant", "unwilling", model="test/model", api_key="test-key", timeout=30
        )
    assert result["prompt_sentence"] == "She was _____ to leave."
    first, second = call.call_args_list
    assert "response_format" in json.loads(first.args[0].data)
    fallback = json.loads(second.args[0].data)
    assert "response_format" not in fallback
    assert "provider" not in fallback
    assert second.kwargs["timeout"] <= first.kwargs["timeout"] <= 30


def test_generic_bad_request_is_not_retried_or_exposed():
    from app.llm import openrouter_review

    error = HTTPError(
        OPENROUTER_URL,
        400,
        "Bad request",
        {},
        io.BytesIO(b'{"error":{"message":"private vocabulary and test-key"}}'),
    )
    with (
        patch.object(openrouter_review, "urlopen", side_effect=error) as call,
        pytest.raises(ReviewError, match="request parameters") as caught,
    ):
        generate_review(
            "reluctant", "unwilling", model="test/model", api_key="test-key"
        )
    call.assert_called_once()
    assert "private vocabulary" not in str(caught.value)
    assert "test-key" not in str(caught.value)
