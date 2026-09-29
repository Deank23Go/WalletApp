from __future__ import annotations

import threading
import time
import uuid
from collections import defaultdict, deque
from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import Settings
from app.core.security import JwtAccessTokenCodec, SystemClock
from app.db.models import User
from app.db.session import SqlAlchemyUnitOfWork
from app.domain.errors import AuthenticationError, DomainValidationError
from app.repositories.users_repo import SqlUserRepository

settings = Settings()  # type: ignore[call-arg]
clock = SystemClock()
bearer_scheme = HTTPBearer(auto_error=False)


class RateLimitExceeded(Exception):
    pass


class FixedWindowRateLimiter:
    def __init__(self) -> None:
        self._attempts: defaultdict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, *, scope: str, client: str, limit: int, now: float | None = None) -> None:
        current_time = time.monotonic() if now is None else now
        threshold = current_time - 60
        key = (scope, client)
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= threshold:
                attempts.popleft()
            if len(attempts) >= limit:
                raise RateLimitExceeded("Se alcanzó el límite de intentos. Intente nuevamente más tarde")
            attempts.append(current_time)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()


rate_limiter = FixedWindowRateLimiter()


def get_uow() -> Generator[SqlAlchemyUnitOfWork, None, None]:
    uow = SqlAlchemyUnitOfWork()
    try:
        yield uow
        uow.commit()
    except Exception:
        uow.rollback()
        raise
    finally:
        uow.close()


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    uow: Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)],
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("Debe iniciar sesión para continuar")
    codec = JwtAccessTokenCodec(
        secret=settings.jwt_secret.get_secret_value(),
        issuer=settings.jwt_issuer,
        ttl_seconds=settings.jwt_ttl_seconds,
        clock=clock,
    )
    user_id = codec.decode_subject(credentials.credentials)
    user = SqlUserRepository(uow.session).get_by_id(user_id)
    if user is None:
        raise AuthenticationError("La sesión no es válida")
    return user


def require_idempotency_key(
    value: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> uuid.UUID:
    if value is None:
        raise DomainValidationError("Debe enviar la cabecera Idempotency-Key", field="Idempotency-Key")
    try:
        return uuid.UUID(value)
    except ValueError as error:
        raise DomainValidationError("Idempotency-Key debe ser un UUID válido", field="Idempotency-Key") from error


def _client_identifier(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def enforce_register_rate_limit(request: Request) -> None:
    rate_limiter.check(
        scope="auth.register",
        client=_client_identifier(request),
        limit=settings.register_rate_limit_per_minute,
    )


def enforce_login_rate_limit(request: Request) -> None:
    rate_limiter.check(
        scope="auth.login",
        client=_client_identifier(request),
        limit=settings.login_rate_limit_per_minute,
    )


UnitOfWorkDep = Annotated[SqlAlchemyUnitOfWork, Depends(get_uow)]
CurrentUserDep = Annotated[User, Depends(get_current_user)]
IdempotencyKeyDep = Annotated[uuid.UUID, Depends(require_idempotency_key)]
