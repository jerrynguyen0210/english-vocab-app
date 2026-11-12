import pytest

from app.services.reviews.prompts import mask_target, prompt_sentence


@pytest.mark.parametrize(
    ("text", "word", "expected"),
    [
        ("Hello, HELLO! hello.", "hello", "_____, _____! _____."),
        ("She showed resilience.", "resilience", "She showed _____."),
        ("An unrelated hint.", "hello", "An unrelated hint."),
        ("Try C++ and c++.", "C++", "Try _____ and _____."),
        ("Take\na break; take a break.", "take a break", "_____; _____."),
        ("ＳＴＲＡＳＳＥ and Straße.", "straße", "_____ and _____."),
        ("Her kindness was kind.", "kind", "Her _____ness was _____."),
        ("", "hello", ""),
        ("He was **ready** to leave.", "ready", "He was _____ to leave."),
        ("He was **_____** to leave.", "ready", "He was _____ to leave."),
        ("He was ** _____ ** to leave.", "ready", "He was  _____  to leave."),
    ],
)
def test_mask_target(text, word, expected):
    assert mask_target(text, word) == expected


@pytest.mark.parametrize(
    ("example", "explanation", "word", "expected"),
    [
        (
            "Her RESILIENCE helped; resilience matters.",
            "Ability to recover.",
            "resilience",
            "Her _____ helped; _____ matters.",
        ),
        ("Try ＳＴＲＡＳＳＥ and Straße.", "A road.", "straße", "Try _____ and _____."),
        ("We take\na break at noon.", "To pause.", "take a break", "We _____ at noon."),
        (None, "A greeting.", "hello", "“_____” means: A greeting."),
        ("", "A greeting.", "hello", "“_____” means: A greeting."),
        ("  ", "A greeting.", "hello", "“_____” means: A greeting."),
        (
            "An unrelated sentence.",
            "A greeting.",
            "hello",
            "“_____” means: A greeting.",
        ),
        (
            "There is already a _____ here.",
            "Hello is a greeting.",
            "hello",
            "“_____” means: _____ is a greeting.",
        ),
        (None, "Signifies.", "means", "“_____” _____: Signifies."),
    ],
)
def test_prompt_sentence_always_blanks_target(example, explanation, word, expected):
    assert prompt_sentence(example, explanation, word) == expected
