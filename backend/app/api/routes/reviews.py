import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.reviews import (
    AnswerInput,
    AnswerResult,
    ChoiceRequest,
    ReviewItem,
    ReviewSelection,
    SessionItem,
    TypingSessionItem,
)
from app.services.reviews import service as reviews

router = APIRouter()


@router.get("/reviews/next", response_model=list[ReviewItem])
def next_reviews(
    response: Response,
    db: DB,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=50)] = 1,
) -> list[ReviewItem]:
    with service_errors():
        result = reviews.next_reviews(db, user, limit)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/reviews/summary")
def review_summary(response: Response, db: DB, user: CurrentUser) -> dict[str, int]:
    with service_errors():
        result = reviews.review_summary(db, user)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/reviews/preparation")
def review_preparation(
    response: Response,
    db: DB,
    user: CurrentUser,
    selection: Annotated[ReviewSelection, Query()],
) -> dict[str, int]:
    with service_errors():
        result = reviews.review_preparation(db, user, selection)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/reviews/session", response_model=list[SessionItem | TypingSessionItem])
def review_session(
    response: Response,
    db: DB,
    user: CurrentUser,
    selection: Annotated[ReviewSelection, Query()],
) -> list[TypingSessionItem]:
    with service_errors():
        result = reviews.review_session(db, user, selection)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/reviews/{word_id}/choices", response_model=SessionItem)
def word_choices(
    word_id: uuid.UUID,
    body: ChoiceRequest,
    response: Response,
    db: DB,
    user: CurrentUser,
) -> SessionItem:
    """Reveal D16 options only after an explicit switch to multiple choice."""
    with service_errors():
        result = reviews.word_choices(word_id, body, db, user)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/reviews/{word_id}/answer", response_model=AnswerResult)
def submit_answer(
    word_id: uuid.UUID, body: AnswerInput, response: Response, db: DB, user: CurrentUser
) -> AnswerResult:
    with service_errors():
        result = reviews.submit_answer(word_id, body, db, user)
    response.headers["Cache-Control"] = "no-store"
    return result
