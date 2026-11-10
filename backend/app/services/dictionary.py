"""Local WordNet definitions and lexical families, with LemmInflect verb forms."""

from functools import lru_cache
from threading import RLock
from typing import Any, Literal

from lemminflect import getInflection, getLemma
from nltk.corpus import wordnet
from pydantic import BaseModel

PartOfSpeech = Literal["noun", "verb", "adjective", "adverb", "other"]
VerbForm = Literal["V1", "V2", "V3"]
POS: dict[str, PartOfSpeech] = {
    "n": "noun",
    "v": "verb",
    "a": "adjective",
    "s": "adjective",
    "r": "adverb",
}
TAGS: dict[VerbForm, str] = {"V1": "VB", "V2": "VBD", "V3": "VBN"}
# WordNet's lazy reader and file handles are shared by FastAPI worker threads.
_lock = RLock()


class DictionaryEntry(BaseModel):
    word: str
    part_of_speech: PartOfSpeech
    verb_forms: list[VerbForm] = []
    english_explanation: str
    example_sentence: str | None = None


@lru_cache(maxsize=256)
def _lookup(query: str, include_family: bool) -> tuple[DictionaryEntry, ...]:
    seeds = wordnet.lemmas(query.replace(" ", "_"))
    # WordNet lemmas() only returns exact spellings; resolve inflections first.
    for upos, pos in (("VERB", "v"), ("NOUN", "n"), ("ADJ", "a"), ("ADV", "r")):
        for base in getLemma(query, upos=upos, lemmatize_oov=False) or ():
            seeds.extend(wordnet.lemmas(base.replace(" ", "_"), pos=pos))
    family: dict[str, Any] = {lemma.key(): lemma for lemma in seeds}
    if include_family:
        # Two lexical hops allow create → creative → creativity, without
        # treating synonyms or words with the same prefix as family members.
        frontier = seeds
        for _ in range(2):
            following = []
            for lemma in frontier:
                for related in (
                    lemma.derivationally_related_forms() + lemma.pertainyms()
                ):
                    if related.key() not in family and len(family) < 120:
                        family[related.key()] = related
                        following.append(related)
            frontier = following
        # Adverb pertainyms point toward adjectives, not the reverse. Validate
        # common -ly candidates through that relationship before including them.
        for lemma in list(family.values()):
            if lemma.synset().pos() not in ("a", "s"):
                continue
            name = lemma.name()
            candidates = {name + "ly", name.removesuffix("y") + "ily"}
            for candidate in candidates:
                for adverb in wordnet.lemmas(candidate, pos="r"):
                    if any(parent.name() == name for parent in adverb.pertainyms()):
                        family[adverb.key()] = adverb

    entries: dict[tuple[str, PartOfSpeech], DictionaryEntry] = {}
    for lemma in family.values():
        synset = lemma.synset()
        pos = POS[synset.pos()]
        base = lemma.name().replace("_", " ")
        examples = synset.examples()
        if pos != "verb":
            entries.setdefault(
                (base, pos),
                DictionaryEntry(
                    word=base,
                    part_of_speech=pos,
                    english_explanation=synset.definition(),
                    example_sentence=examples[0] if examples else None,
                ),
            )
            continue
        for form, tag in TAGS.items():
            for spelling in getInflection(base, tag=tag) or ():
                key = (spelling, pos)
                if key not in entries:
                    explanation = synset.definition()
                    if spelling != base:
                        explanation = f"Verb form of {base}: {explanation}"
                    entries[key] = DictionaryEntry(
                        word=spelling,
                        part_of_speech=pos,
                        english_explanation=explanation,
                        example_sentence=examples[0]
                        if examples and spelling == base
                        else None,
                    )
                if form not in entries[key].verb_forms:
                    entries[key].verb_forms.append(form)
    return tuple(entries.values())


def search_dictionary(
    query: str, include_family: bool, parts: list[PartOfSpeech], forms: list[VerbForm]
) -> list[DictionaryEntry]:
    with _lock:
        entries = _lookup(query, include_family)
        results = []
        for entry in entries:
            if entry.part_of_speech not in parts:
                continue
            selected_forms = [form for form in entry.verb_forms if form in forms]
            if entry.part_of_speech == "verb" and not selected_forms:
                continue
            results.append(entry.model_copy(update={"verb_forms": selected_forms}))
        return sorted(
            results,
            key=lambda item: (item.word != query, item.word, item.part_of_speech),
        )[:60]
