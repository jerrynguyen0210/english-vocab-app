from uuid import UUID

from fastapi import APIRouter, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.common_words import (
    CommonBatch,
    CommonBatchRequest,
    CommonLearnedRequest,
)
from app.services.common_words import get_batch, mark_learned

router = APIRouter()


@router.post("/common-words/{question_id}/learned", status_code=204)
def common_learned(
    question_id: UUID, body: CommonLearnedRequest, db: DB, user: CurrentUser
) -> Response:
    with service_errors():
        mark_learned(db, user, question_id, body.selected_index)
    return Response(status_code=204, headers={"Cache-Control": "no-store"})


@router.post("/common-words/batch", response_model=CommonBatch)
def common_batch(
    body: CommonBatchRequest, response: Response, db: DB, user: CurrentUser
) -> CommonBatch:
    with service_errors():
        result = get_batch(db, user, body)
    response.headers["Cache-Control"] = "no-store"
    if result.status == "pending":
        response.status_code = 202
        response.headers["Retry-After"] = "2"
    return result
