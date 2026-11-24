"""Common generation stays bounded and validates the supplied bank IDs exactly."""

import io
import json
from unittest.mock import patch
from urllib.error import HTTPError
from uuid import uuid4

import pytest

from app.llm.openrouter_common import generate_common_questions
from app.llm.openrouter_review import ReviewError
from app.schemas.common_words import BankWord

WORDS = [
    BankWord(
        id=uuid4(),
        word="reliable",
        ipa=None,
        part_of_speech="adjective",
        english_explanation="Able to be trusted.",
        example_sentence=None,
    )
]
QUESTION = {
    "common_word_id": str(WORDS[0].id),
    "question": "What does reliable mean?",
    "choices": ["Able to be trusted", "Easy to break", "Very slow", "Too expensive"],
    "correct_index": 0,
}


def completion(questions=None, finish="stop"):
    return io.BytesIO(
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": finish,
                        "message": {
                            "content": json.dumps(
                                {
                                    "questions": questions
                                    if questions is not None
                                    else [QUESTION]
                                }
                            )
                        },
                    }
                ]
            }
        ).encode()
    )


def generate():
    return generate_common_questions(
        WORDS, model="test/model", api_key="placeholder", timeout=15
    )


def rejection(kind, status=400):
    message = {
        "reasoning": "Reasoning is mandatory and cannot be disabled",
        "schema": "response_format json_schema not supported",
    }[kind]
    return HTTPError(
        "https://example.test",
        status,
        "Rejected",
        {},
        io.BytesIO(json.dumps({"error": {"message": message}}).encode()),
    )


def test_supplied_words_and_schema_are_sent_and_output_is_validated():
    with patch(
        "app.llm.openrouter_common.urlopen", return_value=completion()
    ) as request:
        assert generate()[0].common_word_id == WORDS[0].id
    payload = json.loads(request.call_args.args[0].data)
    assert json.loads(payload["messages"][1]["content"])[0]["word"] == "reliable"
    assert payload["response_format"]["json_schema"]["strict"] is True
    assert request.call_args.kwargs["timeout"] <= 15


@pytest.mark.parametrize(
    "changes",
    [
        {"choices": ["one", "two", "three"]},
        {"choices": ["one", "two", "three", " ONE "]},
        {"choices": ["one", "two", "three", " "]},
        {"correct_index": True},
        {"correct_index": 4},
        {"question": " "},
        {"common_word_id": str(uuid4())},
        {"extra": "not allowed"},
    ],
)
def test_invalid_questions_fail_as_whole_batch(changes):
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            return_value=completion([{**QUESTION, **changes}]),
        ),
        pytest.raises(ReviewError),
    ):
        generate()


@pytest.mark.parametrize("questions", [[], [QUESTION, QUESTION]])
def test_missing_and_duplicate_ids_rejected(questions):
    with (
        patch("app.llm.openrouter_common.urlopen", return_value=completion(questions)),
        pytest.raises(ReviewError),
    ):
        generate()


def test_truncation_is_rejected():
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            return_value=completion(finish="length"),
        ),
        pytest.raises(ReviewError),
    ):
        generate()


@pytest.mark.parametrize(
    "capabilities",
    [["reasoning"], ["schema"], ["reasoning", "schema"], ["schema", "reasoning"]],
)
def test_capability_fallbacks_are_independent_and_bounded(capabilities):
    with patch(
        "app.llm.openrouter_common.urlopen",
        side_effect=[*(rejection(kind) for kind in capabilities), completion()],
    ) as request:
        assert generate()
    assert request.call_count == len(capabilities) + 1
    payload = json.loads(request.call_args.args[0].data)
    if "schema" in capabilities:
        assert "response_format" not in payload
    if "reasoning" in capabilities:
        assert "reasoning" not in payload and payload["max_tokens"] == 16000


@pytest.mark.parametrize("status", [401, 402, 429, 500])
def test_noncapability_errors_are_not_retried(status):
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            side_effect=rejection("reasoning", status),
        ) as request,
        pytest.raises(ReviewError),
    ):
        generate()
    assert request.call_count == 1


def test_repeated_reasoning_rejection_does_not_loop():
    with (
        patch(
            "app.llm.openrouter_common.urlopen",
            side_effect=[rejection("reasoning"), rejection("reasoning")],
        ) as request,
        pytest.raises(ReviewError),
    ):
        generate()
    assert request.call_count == 2
