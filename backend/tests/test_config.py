import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_load_required_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://wallet:secret@localhost/walletapp")
    monkeypatch.setenv("JWT_SECRET", "test-secret")

    settings = Settings(_env_file=None)

    assert settings.database_url == "postgresql+psycopg://wallet:secret@localhost/walletapp"
    assert settings.jwt_secret.get_secret_value() == "test-secret"
    assert settings.jwt_ttl_seconds == 900
    assert settings.register_rate_limit_per_minute == 5
    assert settings.login_rate_limit_per_minute == 10


def test_settings_allow_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://wallet:secret@localhost/walletapp")
    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("JWT_TTL_SECONDS", "600")
    monkeypatch.setenv("REGISTER_RATE_LIMIT_PER_MINUTE", "3")
    monkeypatch.setenv("LOGIN_RATE_LIMIT_PER_MINUTE", "7")

    settings = Settings(_env_file=None)

    assert settings.jwt_ttl_seconds == 600
    assert settings.register_rate_limit_per_minute == 3
    assert settings.login_rate_limit_per_minute == 7


def test_settings_reject_missing_jwt_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://wallet:secret@localhost/walletapp")
    monkeypatch.delenv("JWT_SECRET", raising=False)

    with pytest.raises(ValidationError, match="jwt_secret"):
        Settings(_env_file=None)
