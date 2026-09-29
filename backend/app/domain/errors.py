from __future__ import annotations


class DomainError(Exception):
    def __init__(self, message: str, *, field: str = "general") -> None:
        super().__init__(message)
        self.message = message
        self.field = field


class DomainValidationError(DomainError):
    pass


class ResourceNotFoundError(DomainError):
    pass


class DomainConflictError(DomainError):
    pass


class AuthenticationError(DomainError):
    pass


class RefreshTokenReuseError(AuthenticationError):
    pass


class ConcurrencyError(DomainConflictError):
    pass


class IdempotencyError(DomainConflictError):
    pass
