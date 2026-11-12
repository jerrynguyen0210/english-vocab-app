"""Answer normalization and exact-spelling comparison."""


def answer_matches(typed_answer: str, saved_word: str) -> bool:
    """D2: ignore case and outer whitespace, otherwise require exact spelling."""
    return normalise_answer(typed_answer) == normalise_answer(saved_word)


def normalise_answer(value: str) -> str:
    return value.strip().casefold()
