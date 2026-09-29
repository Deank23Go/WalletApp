from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import Money, PositiveMoney

MovementType = Literal["INCOME", "EXPENSE"]


class MovementCreateRequest(BaseModel):
    type: MovementType
    account_id: uuid.UUID
    category_id: uuid.UUID
    amount: PositiveMoney
    date: date
    note: str | None = Field(default=None, max_length=255)


class MovementResponse(BaseModel):
    id: uuid.UUID
    type: MovementType
    status: Literal["POSTED", "VOIDED"]
    account_id: uuid.UUID
    category_id: uuid.UUID
    amount: Money
    date: date
    note: str | None = None


class MovementCreateResponse(BaseModel):
    movement: MovementResponse
    new_balance: Money


class VoidMovementSummary(BaseModel):
    id: uuid.UUID
    type: Literal["VOID"] = "VOID"
    status: Literal["POSTED"] = "POSTED"
    voided_journal_id: uuid.UUID
    date: date


class VoidMovementResponse(BaseModel):
    void_movement: VoidMovementSummary
    new_balance: Money
    negative_balance_warning: bool


class ResourceSummary(BaseModel):
    id: uuid.UUID
    name: str


class MovementHistoryItem(BaseModel):
    id: uuid.UUID
    type: Literal["OPENING", "INCOME", "EXPENSE", "VOID"]
    status: Literal["POSTED", "VOIDED"]
    date: date
    amount: Money
    note: str | None = None
    account: ResourceSummary
    category: ResourceSummary | None = None


class MovementHistoryResponse(BaseModel):
    items: list[MovementHistoryItem]
    page: int
    page_size: int
    total: int


class MovementFilters(BaseModel):
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=50, ge=1, le=100)

    @model_validator(mode="after")
    def validate_date_range(self) -> MovementFilters:
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("La fecha inicial no puede ser posterior a la fecha final")
        return self
