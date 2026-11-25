"""Authenticated transport stubs. Teacher directory and assignment are deferred."""

from fastapi import APIRouter, HTTPException, Response

from app.api.dependencies import CurrentUser
from app.schemas.teachers import (
    TeacherSelection,
    TeacherSelectionOptions,
    TeacherSelectionUpdate,
)

router = APIRouter()


@router.get("/teachers", response_model=TeacherSelectionOptions)
def get_teachers(response: Response, user: CurrentUser) -> TeacherSelectionOptions:
    # TODO: Load the directory and the user's selection from the business layer.
    response.headers["Cache-Control"] = "no-store"
    return TeacherSelectionOptions(teachers=[], selected_teacher_id=None)


@router.put("/teachers/selection", response_model=TeacherSelection)
def select_teacher(body: TeacherSelectionUpdate, user: CurrentUser) -> TeacherSelection:
    # TODO: Validate availability and persist the selection in the business layer.
    # Never acknowledge a successful save until assignment is actually implemented.
    raise HTTPException(
        status_code=501, detail="Teacher selection is not available yet."
    )
