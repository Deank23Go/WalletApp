from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import Money, NonNegativeMoney


class AccountCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    type: Literal["CASH", "BANK"]
    opening_balance: NonNegativeMoney = Decimal("0.00")

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized_name = value.strip()
        if not normalized_name:
            raise ValueError("El nombre es obligatorio")
        return normalized_name


class AccountUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    status: Literal["INACTIVE"] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized_name = value.strip()
        if not normalized_name:
            raise ValueError("El nombre es obligatorio")
        return normalized_name

    @model_validator(mode="after")
    def require_change(self) -> AccountUpdateRequest:
        if self.name is None and self.status is None:
            raise ValueError("Debe enviar al menos un cambio")
        if self.name is not None and self.status is not None:
            raise ValueError("Debe enviar un solo cambio por solicitud")
        return self


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: Literal["CASH", "BANK"]
    status: Literal["ACTIVE", "INACTIVE"]
    balance: Money
    currency: str
