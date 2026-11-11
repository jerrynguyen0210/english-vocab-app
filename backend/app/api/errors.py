"""Keep HTTP status codes out of business services."""

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi import HTTPException

from app.services.errors import (
    AccountUnavailable,
    AuthRateLimited,
    DictionaryUnavailable,
    InvalidAccessToken,
    InvalidCredentials,
    InvalidSearch,
    InvalidSession,
    RegistrationConflict,
    ReviewConflict,
    ReviewGenerationUnavailable,
    ReviewNotFound,
    ServiceError,
    WordAlreadyExists,
)

_STATUS_CODES = {
    AccountUnavailable: 401,
    AuthRateLimited: 429,
    InvalidCredentials: 401,
    InvalidSession: 401,
    InvalidAccessToken: 401,
    RegistrationConflict: 409,
    InvalidSearch: 422,
    DictionaryUnavailable: 503,
    WordAlreadyExists: 409,
    ReviewNotFound: 404,
    ReviewGenerationUnavailable: 503,
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
        headers = None
        if isinstance(error, AuthRateLimited):
            headers = {"Retry-After": str(error.retry_after)}
        elif isinstance(error, InvalidAccessToken):
            headers = {"WWW-Authenticate": "Bearer"}
        raise HTTPException(status, str(error), headers=headers) from None
