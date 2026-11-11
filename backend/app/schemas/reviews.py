import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.word import normalise_word


class ReviewItem(BaseModel):
    word_id: uuid.UUID
    english_explanation: str
    example_sentence: str | None = None


class TypingSessionItem(ReviewItem):
    prompt_sentence: str
    attempt_id: uuid.UUID
    review_token: str


class SessionItem(TypingSessionItem):
    choices: list[str] = Field(min_length=4, max_length=4)

    @field_validator("choices")
    @classmethod
    def four_unique_choices(cls, values: list[str]) -> list[str]:
        if (
            len(values) != 4
            or any(not normalise_word(value) for value in values)
            or len({normalise_word(value) for value in values}) != 4
        ):
            raise ValueError("Multiple choice requires four distinct nonblank options")
        return values


class ChoiceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: uuid.UUID
    review_token: str = Field(max_length=4096)


class AnswerInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attempt_id: uuid.UUID | None = None
    review_token: str | None = Field(default=None, max_length=4096)
    typed_answer: str = Field(max_length=200)
    time_taken_ms: int = Field(ge=0, le=2147483647, strict=True)


class AnswerResult(BaseModel):
    attempt_id: uuid.UUID
    result: Literal["correct", "incorrect"]
    correct_word: str
    next_due_at: datetime
