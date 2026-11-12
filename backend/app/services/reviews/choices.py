"""D16: server-owned, tiered distractors and exactly four unique options."""

from collections.abc import Mapping
from secrets import SystemRandom

from app.core.text import normalise_word
from app.services.dictionary import PartOfSpeech, review_family, review_parts

# General dictionary vocabulary is the approved last tier for small banks,
# including custom words without a WordNet entry or a lexical family.
GENERAL_VOCABULARY: dict[PartOfSpeech, tuple[str, ...]] = {
    "noun": ("journey", "garden", "purpose", "balance", "memory", "shelter"),
    "verb": ("discover", "improve", "gather", "explain", "protect", "compare"),
    "adjective": ("careful", "bright", "gentle", "patient", "useful", "honest"),
    "adverb": ("quietly", "clearly", "often", "nearly", "slowly", "always"),
    "other": (),
}


def review_options(
    target: str, saved_parts: Mapping[str, frozenset[PartOfSpeech]]
) -> list[str]:
    rng = SystemRandom()
    parts = saved_parts.get(target)
    if parts is None:
        parts = review_parts(target)
    distractors: list[str] = []
    seen = {normalise_word(target)}

    def add_tier(candidates: list[str]) -> None:
        rng.shuffle(candidates)
        for candidate in candidates:
            key = normalise_word(candidate)
            if len(distractors) == 3:
                return
            if key and len(candidate) <= 200 and key not in seen:
                seen.add(key)
                distractors.append(candidate)

    add_tier(
        [
            word
            for word, candidate_parts in saved_parts.items()
            if parts & candidate_parts
        ]
    )
    if len(distractors) < 3:
        add_tier(list(review_family(target)))
    if len(distractors) < 3:
        add_tier(list(saved_parts))
    if len(distractors) < 3:
        add_tier(
            [
                word
                for pos, words in GENERAL_VOCABULARY.items()
                if pos in parts
                for word in words
            ]
        )
    if len(distractors) < 3:
        add_tier([word for words in GENERAL_VOCABULARY.values() for word in words])
    options = [target, *distractors]
    rng.shuffle(options)
    return options
