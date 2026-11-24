"""Common practice contracts; answer keys are never part of a batch response."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.text import normalise_word


class BankWord(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    word: str
    ipa: str | None
    part_of_speech: str
    english_explanation: str
    example_sentence: str | None


class GeneratedCommonQuestion(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    common_word_id: UUID
    question: str = Field(min_length=1, max_length=1000)
    choices: list[str] = Field(min_length=4, max_length=4)
    correct_index: int = Field(ge=0, le=3, strict=True)

    @field_validator("choices")
    @classmethod
    def distinct_choices(cls, values: list[str]) -> list[str]:
        values = [value.strip() for value in values]
        if (
            any(not normalise_word(value) or len(value) > 500 for value in values)
            or len({normalise_word(value) for value in values}) != 4
        ):
            raise ValueError("Four distinct nonblank choices are required")
        return values


class GeneratedCommonBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    questions: list[GeneratedCommonQuestion] = Field(min_length=1, max_length=10)


class CommonQuestion(BaseModel):
    id: UUID
    word: str
    ipa: str | None
    partOfSpeech: str
    explanation: str
    example: str | None
    question: str
    choices: list[str]


class CommonBatch(BaseModel):
    status: Literal["ready", "complete"]
    questions: list[CommonQuestion] = Field(default_factory=list)


class CommonBatchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommonAnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    selected_index: int = Field(ge=0, le=3, strict=True)


class CommonAnswerResult(BaseModel):
    result: Literal["correct", "incorrect"]
    correctIndex: int
    explanation: str


class CommonBatchStatus(BaseModel):
    id: UUID
    status: Literal["pending", "generating", "ready", "complete", "failed"]
    questions: list[CommonQuestion] = Field(default_factory=list)
