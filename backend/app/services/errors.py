"""Business failures translated to HTTP responses by the API layer."""


class ServiceError(Exception):
    pass


class TopicSearchUnavailable(ServiceError):
    pass


class TopicIndexPending(ServiceError):
    pass


class AccountUnavailable(ServiceError):
    pass


class InvalidSearch(ServiceError):
    pass


class DictionaryUnavailable(ServiceError):
    pass


class WordAlreadyExists(ServiceError):
    pass


class ReviewNotFound(ServiceError):
    pass


class ReviewConflict(ServiceError):
    pass


class InvalidCredentials(ServiceError):
    pass


class InvalidSession(ServiceError):
    pass


class InvalidAccessToken(ServiceError):
    pass


class RegistrationConflict(ServiceError):
    pass


class AuthRateLimited(ServiceError):
    def __init__(self, retry_after: int) -> None:
        super().__init__("Too many authentication attempts")
        self.retry_after = retry_after


class ReviewGenerationUnavailable(ServiceError):
    pass
