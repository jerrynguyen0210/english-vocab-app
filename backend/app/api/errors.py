"""Keep HTTP status codes out of business services."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from app.services.errors import (
    AccountUnavailable,
    DictionaryUnavailable,
    InvalidSearch,
    ReviewConflict,
    ReviewNotFound,
    ServiceError,
    WordAlreadyExists,
)

_STATUS_CODES = {
    AccountUnavailable: 401,
    InvalidSearch: 422,
    DictionaryUnavailable: 503,
    WordAlreadyExists: 409,
    ReviewNotFound: 404,
    ReviewConflict: 409,
}


@contextmanager
def service_errors() -> Iterator[None]:
    try:
        yield
    except ServiceError as error:
        status = _STATUS_CODES.get(type(error))
        if status is None:
            raise
        raise HTTPException(status, str(error)) from None
