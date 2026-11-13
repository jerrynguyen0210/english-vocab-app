"""Validate model output before it can enter a user's question bank."""

import re
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.text import normalise_word

ShortText = Annotated[str, Field(min_length=1, max_length=200)]


class GeneratedCommonWord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    word: str = Field(min_length=1, max_length=80)
    ipa: str = Field(min_length=3, max_length=120, pattern=r"^/[^/\r\n]+/$")
    part_of_speech: Literal[
        "noun",
        "verb",
        "adjective",
        "adverb",
        "preposition",
        "conjunction",
        "interjection",
    ]
    explanation: str = Field(min_length=1, max_length=500)
    example: ShortText
    choices: list[ShortText] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3)

    @field_validator("word")
    @classmethod
    def english_word(cls, value: str) -> str:
        value = normalise_word(value)
        if not re.fullmatch(r"[a-z]+(?:[-'][a-z]+)*", value):
            raise ValueError("Expected an English word")
        return value

    @model_validator(mode="after")
    def usable_question(self) -> "GeneratedCommonWord":
        if len({normalise_word(choice) for choice in self.choices}) != 4:
            raise ValueError("Answer choices must be distinct")
        if not re.search(
            rf"(?<!\w){re.escape(self.word)}(?!\w)", normalise_word(self.example)
        ):
            raise ValueError("Example must contain the target word")
        return self


class GeneratedCommonWords(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    words: list[GeneratedCommonWord] = Field(min_length=1, max_length=20)


class CommonBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exclude_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)


class CommonLearnedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    selected_index: int = Field(ge=0, le=3)


class CommonQuestion(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    id: uuid.UUID
    word: str
    ipa: str | None = None
    part_of_speech: str = Field(serialization_alias="partOfSpeech")
    explanation: str
    example: str
    choices: list[str]
    correct_index: int = Field(serialization_alias="correctIndex")


class CommonBatch(BaseModel):
    status: Literal["ready", "pending", "failed"]
    questions: list[CommonQuestion] = Field(default_factory=list)
