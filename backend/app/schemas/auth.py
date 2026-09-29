from __future__ import annotations

import re
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class EmailRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized_email = value.strip().lower()
        if EMAIL_PATTERN.fullmatch(normalized_email) is None:
            raise ValueError("El correo no tiene un formato válido")
        return normalized_email


class RegisterRequest(EmailRequest):
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    preferred_currency: str
    created_at: datetime | None = None


class SessionResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
