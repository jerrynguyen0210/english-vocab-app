from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.common_words import (
    CommonAnswerInput,
    CommonAnswerResult,
    CommonBatch,
    CommonBatchRequest,
    CommonBatchStatus,
)
from app.services.common_batches import read_batch, start_batch
from app.services.common_words import answer_question, get_batch

router = APIRouter()


@router.post("/common-words/batch", response_model=CommonBatch)
def common_batch(
    body: CommonBatchRequest, response: Response, db: DB, user: CurrentUser
) -> CommonBatch:
    with service_errors():
        result = get_batch(db, user)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post(
    "/common-words/questions/{question_id}/answer", response_model=CommonAnswerResult
)
def common_answer(
    question_id: UUID,
    body: CommonAnswerInput,
    response: Response,
    db: DB,
    user: CurrentUser,
) -> CommonAnswerResult:
    with service_errors():
        result = answer_question(db, user, question_id, body.selected_index)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/common-words/batches", response_model=CommonBatchStatus, status_code=202)
def start_common_batch(
    response: Response, db: DB, user: CurrentUser
) -> CommonBatchStatus:
    with service_errors():
        result = start_batch(db, user)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.get("/common-words/batches/{batch_id}", response_model=CommonBatchStatus)
def common_batch_status(
    batch_id: UUID, response: Response, db: DB, user: CurrentUser
) -> CommonBatchStatus:
    with service_errors():
        result = read_batch(db, user, batch_id)
    response.headers["Cache-Control"] = "no-store"
    return result
