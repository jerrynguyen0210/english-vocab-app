import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.text import normalise_word


class ReviewSelection(BaseModel):
    source: Literal["time", "recall", "topic"] = "recall"
    topic: str = Field(default="", max_length=200)
    period: Literal["Yesterday", "Weekly", "Monthly"] = "Weekly"
    include_overdue: bool = True
    answer_mode: Literal["typing", "choice"] = "typing"

    @model_validator(mode="after")
    def validate_topic(self) -> "ReviewSelection":
        self.topic = self.topic.strip()
        if self.source == "topic" and not self.topic:
            raise ValueError("Enter a topic to search.")
        return self


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
