from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import date, datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher as Argon2Hasher
from argon2.exceptions import InvalidHashError, VerificationError
from argon2.low_level import Type
from jwt import InvalidTokenError

from app.domain.errors import AuthenticationError
from app.domain.ports import AccessToken, AccessTokenCodec, Clock, PasswordHasher, RefreshTokenCodec, RefreshTokenValue


class SystemClock(Clock):
    def today(self) -> date:
        return self.now().date()

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class Argon2PasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self._hasher = Argon2Hasher(type=Type.ID)

    def hash(self, plaintext: str) -> str:
        return self._hasher.hash(plaintext)

    def verify(self, plaintext: str, hashed: str) -> bool:
        try:
            return self._hasher.verify(hashed, plaintext)
        except (VerificationError, InvalidHashError):
            return False


class JwtAccessTokenCodec(AccessTokenCodec):
    def __init__(self, *, secret: str, issuer: str, ttl_seconds: int, clock: Clock) -> None:
        self._secret = secret
        self._issuer = issuer
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    def issue(self, user_id: uuid.UUID) -> AccessToken:
        issued_at = self._clock.now()
        expires_at = issued_at + timedelta(seconds=self._ttl_seconds)
        token = jwt.encode(
            {
                "sub": str(user_id),
                "iss": self._issuer,
                "iat": issued_at,
                "exp": expires_at,
            },
            self._secret,
            algorithm="HS256",
        )
        return AccessToken(value=token, expires_in=self._ttl_seconds)

    def decode_subject(self, token: str) -> uuid.UUID:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=self._issuer,
                options={"require": ["sub", "iss", "iat", "exp"]},
            )
            return uuid.UUID(payload["sub"])
        except (InvalidTokenError, KeyError, TypeError, ValueError) as error:
            raise AuthenticationError("La sesión no es válida") from error


class OpaqueRefreshTokenCodec(RefreshTokenCodec):
    def generate(self) -> RefreshTokenValue:
        plaintext = secrets.token_urlsafe(48)
        return RefreshTokenValue(plaintext=plaintext, token_hash=self.hash(plaintext))

    def hash(self, plaintext: str) -> str:
        return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()
