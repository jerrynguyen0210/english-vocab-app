"""Business errors retain their HTTP contract without hiding unexpected failures."""

import pytest
from fastapi import HTTPException

from app.api.errors import service_errors
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
    ReviewNotFound,
    ServiceError,
    WordAlreadyExists,
)


@pytest.mark.parametrize(
    ("error_type", "status"),
    [
        (AccountUnavailable, 401),
        (InvalidCredentials, 401),
        (InvalidSession, 401),
        (InvalidAccessToken, 401),
        (RegistrationConflict, 409),
        (InvalidSearch, 422),
        (DictionaryUnavailable, 503),
        (WordAlreadyExists, 409),
        (ReviewNotFound, 404),
        (ReviewConflict, 409),
    ],
)
def test_business_errors_preserve_status_and_detail(error_type, status):
    with pytest.raises(HTTPException) as caught, service_errors():
        raise error_type("Original business failure")
    assert caught.value.status_code == status
    assert caught.value.detail == "Original business failure"


@pytest.mark.parametrize(
    "error", [RuntimeError("unexpected"), ServiceError("unmapped")]
)
def test_unexpected_errors_are_not_misreported_as_client_failures(error):
    with pytest.raises(type(error)) as caught, service_errors():
        raise error
    assert caught.value is error


@pytest.mark.parametrize(
    ("error", "status", "headers"),
    [
        (AuthRateLimited(60), 429, {"Retry-After": "60"}),
        (
            InvalidAccessToken("Invalid or expired access token"),
            401,
            {"WWW-Authenticate": "Bearer"},
        ),
    ],
)
def test_auth_errors_preserve_required_response_headers(error, status, headers):
    with pytest.raises(HTTPException) as caught, service_errors():
        raise error
    assert caught.value.status_code == status
    assert caught.value.headers == headers
    assert caught.value.detail == str(error)
