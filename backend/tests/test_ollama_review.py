"""Offline tests for Ollama prompt generation and response validation."""

import io
import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from app.llm.ollama_review import OLLAMA_URL, ReviewError, generate_review


class ReviewTests(unittest.TestCase):
    def response(self, sentence: str) -> io.BytesIO:
        return io.BytesIO(
            json.dumps(
                {"done": True, "response": json.dumps({"sentence": sentence})}
            ).encode()
        )

    def test_request_and_masked_output(self) -> None:
        with patch(
            "app.llm.ollama_review.urlopen",
            return_value=self.response(
                "She was reluctant to leave her friends behind."
            ),
        ) as call:
            result = generate_review("reluctant", "unwilling", model="local-model")
        self.assertEqual(
            result,
            {
                "prompt_sentence": "She was _____ to leave her friends behind.",
                "answer": "reluctant",
            },
        )
        request = call.call_args.args[0]
        self.assertEqual(request.full_url, f"{OLLAMA_URL}/api/generate")
        payload = json.loads(request.data)
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "local-model")
        self.assertEqual(payload["format"]["required"], ["sentence"])

    def test_rejects_missing_repeated_or_embedded_answer(self) -> None:
        for sentence in ("She left early.", "Go go home.", "The mango is ripe."):
            with (
                self.subTest(sentence=sentence),
                patch(
                    "app.llm.ollama_review.urlopen",
                    return_value=self.response(sentence),
                ),
                self.assertRaises(ReviewError),
            ):
                generate_review("go", "move", model="local-model")

    def test_phrase_and_unicode(self) -> None:
        with patch(
            "app.llm.ollama_review.urlopen",
            return_value=self.response("Please TAKE   OFF your coat."),
        ):
            self.assertEqual(
                generate_review("take off", "remove", model="local-model")[
                    "prompt_sentence"
                ],
                "Please _____ your coat.",
            )

    def test_invalid_response(self) -> None:
        for content in (b"not json", b"{}", b'{"done": true, "response": "[]"}'):
            with (
                patch(
                    "app.llm.ollama_review.urlopen", return_value=io.BytesIO(content)
                ),
                self.assertRaises(ReviewError),
            ):
                generate_review("go", "move", model="local-model")

    def test_connection_failure(self) -> None:
        with (
            patch("app.llm.ollama_review.urlopen", side_effect=URLError("refused")),
            self.assertRaisesRegex(ReviewError, "Cannot reach Ollama"),
        ):
            generate_review("go", "move", model="local-model")


if __name__ == "__main__":
    unittest.main()
