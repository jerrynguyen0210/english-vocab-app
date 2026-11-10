import pytest

from app.services.review_prompt import mask_target


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
    ],
)
def test_mask_target(text, word, expected):
    assert mask_target(text, word) == expected
