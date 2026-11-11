from typing import Annotated

from fastapi import APIRouter, Query, Response

from app.api.dependencies import DB, CurrentUser
from app.api.errors import service_errors
from app.schemas.words import CreateWord, WordCreated, WordSearchResult
from app.services import words
from app.services.dictionary import PartOfSpeech, VerbForm

router = APIRouter()


@router.get("/words/search", response_model=list[WordSearchResult])
def find_words(
    user: CurrentUser,
    db: DB,
    response: Response,
    q: Annotated[str, Query(min_length=1, max_length=200)],
    include_family: bool = True,
    parts: Annotated[list[PartOfSpeech] | None, Query()] = None,
    forms: Annotated[list[VerbForm] | None, Query()] = None,
) -> list[WordSearchResult]:
    with service_errors():
        result = words.find_words(user, db, q, include_family, parts, forms)
    response.headers["Cache-Control"] = "no-store"
    return result


@router.post("/words", status_code=201, response_model=WordCreated)
def create_word(
    body: CreateWord, response: Response, db: DB, user: CurrentUser
) -> WordCreated:
    with service_errors():
        result = words.create_word(body, db, user)
    response.headers["Cache-Control"] = "no-store"
    return result
