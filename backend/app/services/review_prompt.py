"""Prepare recall hints without leaking the answer to the client."""

import re
import unicodedata

from app.models.word import normalise_word


def mask_target(text: str, word: str) -> str:
    """Mask every occurrence, including case/compatibility and spacing variants.

    Match substrings conservatively so compounds cannot disclose the answer.
    Keep an index map because case folding can expand characters (ß -> ss).
    """
    text = unicodedata.normalize("NFKC", text)
    folded = ""
    positions = []
    for index, char in enumerate(text):
        part = char.casefold()
        folded += part
        positions.extend([index] * len(part))
    target = normalise_word(word)
    if not target:
        return "_____"
    pattern = r"\s+".join(re.escape(part) for part in target.split())
    spans: list[tuple[int, int]] = []
    for match in re.finditer(pattern, folded):
        start, end = positions[match.start()], positions[match.end() - 1] + 1
        if spans and start <= spans[-1][1]:
            spans[-1] = (spans[-1][0], end)
        else:
            spans.append((start, end))
    for start, end in reversed(spans):
        text = text[:start] + "_____" + text[end:]
    return text


def prompt_sentence(example: str | None, explanation: str, word: str) -> str:
    """Prefer a saved cloze sentence; definitions keep older words reviewable.

    Only use examples that actually contain the target. A pre-existing blank or
    an unrelated example does not guarantee a usable question. Mask the entire
    fallback too, since the target can also occur in its connective wording.
    """
    if example and example.strip():
        original = unicodedata.normalize("NFKC", example.strip())
        masked = mask_target(original, word)
        if masked != original:
            return masked
    return mask_target(f"“_____” means: {explanation.strip()}", word)
