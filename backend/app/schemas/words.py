import uuid

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.word import normalise_word
from app.services.dictionary import DictionaryEntry


class CreateWord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    word: str = Field(min_length=1, max_length=200)
    english_explanation: str = Field(min_length=1, max_length=5000)

    example_sentence: str | None = Field(default=None, max_length=5000)

    @field_validator("example_sentence")
    @classmethod
    def optional_sentence(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None

    @field_validator("word", "english_explanation")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not normalise_word(value):
            raise ValueError("Must not be blank")
        return value.strip()


class WordCreated(BaseModel):
    example_sentence: str | None = None
    id: uuid.UUID
    word: str
    english_explanation: str


class WordSearchResult(DictionaryEntry):
    saved: bool = False
