from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    jwt_secret: SecretStr
    jwt_issuer: str = Field(default="walletapp", min_length=1)
    jwt_ttl_seconds: int = Field(default=900, gt=0)
    refresh_ttl_seconds: int = Field(default=2_592_000, gt=0)
    refresh_cookie_name: str = Field(default="refresh_token", min_length=1)
    refresh_cookie_path: str = Field(default="/api/v1/auth", min_length=1)
    refresh_cookie_secure: bool = True
    register_rate_limit_per_minute: int = Field(default=5, gt=0)
    login_rate_limit_per_minute: int = Field(default=10, gt=0)
