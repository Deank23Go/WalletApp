from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel

from app.schemas.common import Money


class AccountBalanceResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: Literal["CASH", "BANK"]
    balance: Money


class BalanceResponse(BaseModel):
    consolidated_balance: Money
    currency: str
    accounts: list[AccountBalanceResponse]
