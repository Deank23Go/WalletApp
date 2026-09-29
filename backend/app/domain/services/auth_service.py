from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from app.domain.errors import AuthenticationError, DomainConflictError, DomainValidationError, RefreshTokenReuseError
from app.domain.ports import (
    AccessToken,
    AccessTokenCodec,
    Clock,
    PasswordHasher,
    RefreshTokenCodec,
    RefreshTokenRepository,
)

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class UserStore(Protocol):
    def create(self, *, email: str, password_hash: str, preferred_currency: str = "COP") -> Any: ...
    def get_by_email(self, email: str) -> Any | None: ...
    def get_by_id(self, user_id: uuid.UUID) -> Any | None: ...


class SeedCategoryStore(Protocol):
    def clone_seed_catalog(self) -> int: ...


class SeedCategoryStoreFactory(Protocol):
    def __call__(self, user_id: uuid.UUID) -> SeedCategoryStore: ...


@dataclass(frozen=True)
class SessionResult:
    user: Any
    access_token: AccessToken
    refresh_token: str


class AuthService:
    def __init__(
        self,
        *,
        users: UserStore,
        refresh_tokens: RefreshTokenRepository,
        seed_categories: SeedCategoryStoreFactory,
        password_hasher: PasswordHasher,
        access_tokens: AccessTokenCodec,
        refresh_codec: RefreshTokenCodec,
        clock: Clock,
        refresh_ttl_seconds: int,
    ) -> None:
        self._users = users
        self._refresh_tokens = refresh_tokens
        self._seed_categories = seed_categories
        self._password_hasher = password_hasher
        self._access_tokens = access_tokens
        self._refresh_codec = refresh_codec
        self._clock = clock
        self._refresh_ttl_seconds = refresh_ttl_seconds

    def register(self, *, email: str, password: str) -> Any:
        normalized_email = self._validate_email(email)
        self._validate_password(password)
        if self._users.get_by_email(normalized_email) is not None:
            raise DomainConflictError("Este correo ya está registrado", field="email")
        user = self._users.create(
            email=normalized_email,
            password_hash=self._password_hasher.hash(password),
        )
        self._seed_categories(user.id).clone_seed_catalog()
        return user

    def login(self, *, email: str, password: str) -> SessionResult:
        normalized_email = email.strip().lower()
        user = self._users.get_by_email(normalized_email)
        if user is None or not self._password_hasher.verify(password, user.password_hash):
            raise AuthenticationError("Correo o contraseña incorrectos")
        return self._create_session(user=user, family_id=uuid.uuid4())

    def refresh(self, plaintext_token: str) -> SessionResult:
        now = self._clock.now()
        token_hash = self._refresh_codec.hash(plaintext_token)
        current = self._refresh_tokens.get_by_hash_for_update(token_hash)
        if current is None:
            raise AuthenticationError("La sesión no es válida")
        if current.revoked_at is not None:
            self._refresh_tokens.revoke_family(current.family_id, revoked_at=now)
            raise RefreshTokenReuseError("Se detectó la reutilización de una sesión revocada")
        if current.expires_at <= now:
            self._refresh_tokens.revoke(token_hash, revoked_at=now)
            raise AuthenticationError("La sesión ha expirado")
        user = self._users.get_by_id(current.user_id)
        if user is None:
            raise AuthenticationError("La sesión no es válida")
        if not self._refresh_tokens.revoke(token_hash, revoked_at=now):
            raise AuthenticationError("La sesión no es válida")
        return self._create_session(user=user, family_id=current.family_id)

    def logout(self, plaintext_token: str | None) -> None:
        if plaintext_token is None:
            return
        self._refresh_tokens.revoke(
            self._refresh_codec.hash(plaintext_token),
            revoked_at=self._clock.now(),
        )

    def _create_session(self, *, user: Any, family_id: uuid.UUID) -> SessionResult:
        refresh = self._refresh_codec.generate()
        self._refresh_tokens.create(
            user_id=user.id,
            token_hash=refresh.token_hash,
            family_id=family_id,
            expires_at=self._clock.now() + timedelta(seconds=self._refresh_ttl_seconds),
        )
        return SessionResult(
            user=user,
            access_token=self._access_tokens.issue(user.id),
            refresh_token=refresh.plaintext,
        )

    @staticmethod
    def _validate_email(email: str) -> str:
        normalized_email = email.strip().lower()
        if len(normalized_email) > 254 or EMAIL_PATTERN.fullmatch(normalized_email) is None:
            raise DomainValidationError("El correo no tiene un formato válido", field="email")
        return normalized_email

    @staticmethod
    def _validate_password(password: str) -> None:
        if len(password) < 8:
            raise DomainValidationError("La contraseña debe tener al menos 8 caracteres", field="password")
