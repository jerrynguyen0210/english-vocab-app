"""Answer normalization and exact-spelling comparison."""

from app.core.text import normalise_word


def answer_matches(typed_answer: str, saved_word: str) -> bool:
    """Ignore Unicode compatibility, case, and whitespace; preserve punctuation."""
    return normalise_answer(typed_answer) == normalise_answer(saved_word)


def normalise_answer(value: str) -> str:
    return normalise_word(value)
