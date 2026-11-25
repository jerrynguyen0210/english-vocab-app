"""Authenticated teacher directory and current user's selection."""

from fastapi import APIRouter, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.teachers import (
    TeacherSelection,
    TeacherSelectionOptions,
    TeacherSelectionUpdate,
)
from app.services import teachers

router = APIRouter()


@router.get("/teachers", response_model=TeacherSelectionOptions)
def get_teachers(response: Response, user: CurrentUser) -> TeacherSelectionOptions:
    response.headers["Cache-Control"] = "no-store"
    return teachers.teacher_options(user)


@router.put("/teachers/selection", response_model=TeacherSelection)
def select_teacher(
    body: TeacherSelectionUpdate, response: Response, db: DB, user: CurrentUser
) -> TeacherSelection:
    with service_errors():
        result = teachers.select_teacher(db, user, body.teacher_id)
    response.headers["Cache-Control"] = "no-store"
    return result
