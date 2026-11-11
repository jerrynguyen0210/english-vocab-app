"""Business failures translated to HTTP responses by the API layer."""


class ServiceError(Exception):
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
