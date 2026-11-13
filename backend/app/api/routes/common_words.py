from fastapi import APIRouter, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.common_words import CommonBatch, CommonBatchRequest
from app.services.common_words import get_batch

router = APIRouter()


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
