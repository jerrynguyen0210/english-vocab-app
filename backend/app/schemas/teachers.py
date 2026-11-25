"""Teacher directory and account-owned selection transport contract."""

from pydantic import BaseModel, ConfigDict, Field


class Teacher(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=255)
    model: str


class TeacherSelectionOptions(BaseModel):
    teachers: list[Teacher]
    selected_teacher_id: str | None


class TeacherSelectionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    teacher_id: str = Field(min_length=1, max_length=128)


class TeacherSelection(BaseModel):
    teacher_id: str
