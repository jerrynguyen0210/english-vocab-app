"""Shared vocabulary text normalization."""

import unicodedata


def normalise_word(value: str) -> str:
    """Fold Unicode compatibility, case and whitespace; retain accents/punctuation."""
    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())
