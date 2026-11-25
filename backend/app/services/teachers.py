"""Server-owned teacher catalog and per-user model preferences."""

from importlib.resources import files

from pydantic import TypeAdapter
from sqlalchemy import delete, insert, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PromptJob, User, Word
from app.schemas.teachers import Teacher, TeacherSelection, TeacherSelectionOptions
from app.services.accounts import lock_account
from app.services.errors import InvalidTeacherSelection


def _load_teachers() -> tuple[Teacher, ...]:
    catalog = files("app").joinpath("data/teachers.json").read_text(encoding="utf-8")
    teachers = TypeAdapter(tuple[Teacher, ...]).validate_json(catalog)
    if len({teacher.id for teacher in teachers}) != len(teachers):
        raise ValueError("Teacher catalog IDs must be unique")
    return teachers


# Load and validate once per process. Catalog changes take effect after restart.
TEACHERS = _load_teachers()


def teacher_options(user: User) -> TeacherSelectionOptions:
    return TeacherSelectionOptions(
        teachers=list(TEACHERS), selected_teacher_id=user.selected_teacher_id
    )


def generation_model(user: User) -> str:
    for teacher in TEACHERS:
        if teacher.id == user.selected_teacher_id:
            return teacher.model
    # Accounts without a selection keep their configured generation behavior.
    if user.selected_teacher_id is None:
        return get_settings().openrouter_model
    raise InvalidTeacherSelection(
        "Selected teacher is unavailable. Choose another teacher."
    )


def select_teacher(db: Session, user: User, teacher_id: str) -> TeacherSelection:
    if not any(teacher.id == teacher_id for teacher in TEACHERS):
        raise InvalidTeacherSelection("Choose an available teacher.")
    lock_account(db, user)
    db.refresh(user)  # Compare against the latest selection under the account lock.
    if user.selected_teacher_id != teacher_id:
        user.selected_teacher_id = teacher_id
        word_ids = select(Word.id).where(Word.user_id == user.id)
        # Replacing the jobs also fences old worker lease tokens and resets failed
        # attempts. Other accounts' jobs and review schedules remain untouched.
        db.execute(delete(PromptJob).where(PromptJob.word_id.in_(word_ids)))
        db.execute(insert(PromptJob).from_select(["word_id"], word_ids))
    db.commit()
    return TeacherSelection(teacher_id=teacher_id)
