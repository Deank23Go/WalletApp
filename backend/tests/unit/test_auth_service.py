import uuid
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from app.core.security import Argon2PasswordHasher, OpaqueRefreshTokenCodec
from app.domain.errors import AuthenticationError, DomainConflictError, RefreshTokenReuseError
from app.domain.ports import AccessToken
from app.domain.services.auth_service import AuthService


class FixedClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 9, 28, tzinfo=timezone.utc)

    def today(self) -> date:
        return self.value.date()

    def now(self) -> datetime:
        return self.value


class FakeAccessTokens:
    def issue(self, user_id):
        return AccessToken(value=f"access-{user_id}", expires_in=900)

    def decode_subject(self, token):
        return uuid.UUID(token.removeprefix("access-"))


class FakeUsers:
    def __init__(self) -> None:
        self.items = {}

    def create(self, *, email, password_hash, preferred_currency="COP"):
        user = SimpleNamespace(
            id=uuid.uuid4(),
            email=email,
            password_hash=password_hash,
            preferred_currency=preferred_currency,
        )
        self.items[email] = user
        return user

    def get_by_email(self, email):
        return self.items.get(email)

    def get_by_id(self, user_id):
        return next((item for item in self.items.values() if item.id == user_id), None)


class FakeSeedStore:
    def __init__(self) -> None:
        self.calls = 0

    def clone_seed_catalog(self):
        self.calls += 1
        return 18


class FakeRefreshTokens:
    def __init__(self) -> None:
        self.items = {}

    def create(self, *, user_id, token_hash, family_id, expires_at):
        token = SimpleNamespace(
            user_id=user_id,
            token_hash=token_hash,
            family_id=family_id,
            expires_at=expires_at,
            revoked_at=None,
        )
        self.items[token_hash] = token
        return token

    def get_by_hash_for_update(self, token_hash):
        return self.items.get(token_hash)

    def revoke(self, token_hash, *, revoked_at):
        token = self.items.get(token_hash)
        if token is None or token.revoked_at is not None:
            return False
        token.revoked_at = revoked_at
        return True

    def revoke_family(self, family_id, *, revoked_at):
        count = 0
        for token in self.items.values():
            if token.family_id == family_id and token.revoked_at is None:
                token.revoked_at = revoked_at
                count += 1
        return count


def service_fixture():
    users = FakeUsers()
    refresh_tokens = FakeRefreshTokens()
    seed_stores = {}

    def seeds(user_id):
        seed_stores.setdefault(user_id, FakeSeedStore())
        return seed_stores[user_id]

    service = AuthService(
        users=users,
        refresh_tokens=refresh_tokens,
        seed_categories=seeds,
        password_hasher=Argon2PasswordHasher(),
        access_tokens=FakeAccessTokens(),
        refresh_codec=OpaqueRefreshTokenCodec(),
        clock=FixedClock(),
        refresh_ttl_seconds=3600,
    )
    return service, users, refresh_tokens, seed_stores


def test_register_normalizes_email_hashes_password_and_clones_catalog() -> None:
    service, users, _, seed_stores = service_fixture()

    user = service.register(email="  ANA@EXAMPLE.COM ", password="password-123")

    assert user.email == "ana@example.com"
    assert user.password_hash != "password-123"
    assert seed_stores[user.id].calls == 1
    with pytest.raises(DomainConflictError, match="ya está registrado"):
        service.register(email="ana@example.com", password="password-123")


def test_login_uses_generic_error_and_refresh_rotation_detects_reuse() -> None:
    service, _, refresh_tokens, _ = service_fixture()
    service.register(email="ana@example.com", password="password-123")

    with pytest.raises(AuthenticationError, match="Correo o contraseña incorrectos"):
        service.login(email="ana@example.com", password="incorrect")

    session = service.login(email="ana@example.com", password="password-123")
    rotated = service.refresh(session.refresh_token)

    assert rotated.refresh_token != session.refresh_token
    with pytest.raises(RefreshTokenReuseError, match="reutilización"):
        service.refresh(session.refresh_token)
    assert all(token.revoked_at is not None for token in refresh_tokens.items.values())
