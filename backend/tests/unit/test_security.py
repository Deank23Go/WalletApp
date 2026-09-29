import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from app.core.security import Argon2PasswordHasher, JwtAccessTokenCodec, OpaqueRefreshTokenCodec
from app.domain.errors import AuthenticationError


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.value = now

    def today(self) -> date:
        return self.value.date()

    def now(self) -> datetime:
        return self.value


def test_argon2id_hashes_and_verifies_with_unique_salts() -> None:
    hasher = Argon2PasswordHasher()

    first = hasher.hash("correct-password")
    second = hasher.hash("correct-password")

    assert first.startswith("$argon2id$")
    assert first != "correct-password"
    assert first != second
    assert hasher.verify("correct-password", first) is True
    assert hasher.verify("wrong-password", first) is False


def test_jwt_access_token_contains_valid_subject_and_rejects_expired_token() -> None:
    user_id = uuid.uuid4()
    current = datetime.now(timezone.utc)
    codec = JwtAccessTokenCodec(secret="secret", issuer="walletapp", ttl_seconds=900, clock=FixedClock(current))
    assert codec.decode_subject(codec.issue(user_id).value) == user_id

    expired_codec = JwtAccessTokenCodec(
        secret="secret",
        issuer="walletapp",
        ttl_seconds=1,
        clock=FixedClock(current - timedelta(hours=1)),
    )
    with pytest.raises(AuthenticationError, match="no es válida"):
        codec.decode_subject(expired_codec.issue(user_id).value)


def test_opaque_refresh_tokens_are_random_and_sha256_hashed() -> None:
    codec = OpaqueRefreshTokenCodec()
    first = codec.generate()
    second = codec.generate()

    assert first.plaintext != second.plaintext
    assert first.token_hash != first.plaintext
    assert first.token_hash == codec.hash(first.plaintext)
    assert len(first.token_hash) == 64
