from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

AccountType = Literal["CASH", "BANK"]
AccountStatus = Literal["ACTIVE", "INACTIVE"]
CategoryType = Literal["INCOME", "EXPENSE"]
CategoryStatus = Literal["ACTIVE", "INACTIVE"]
JournalKind = Literal["OPENING", "INCOME", "EXPENSE", "VOID"]
JournalStatus = Literal["POSTED", "VOIDED"]
LineDirection = Literal["DEBIT", "CREDIT"]


@dataclass(frozen=True, slots=True)
class User:
    id: uuid.UUID
    email: str
    preferred_currency: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Account:
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: AccountType
    status: AccountStatus
    version: int
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class Category:
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    type: CategoryType
    is_seed: bool
    status: CategoryStatus
    created_at: datetime


@dataclass(frozen=True, slots=True)
class Journal:
    id: uuid.UUID
    user_id: uuid.UUID
    kind: JournalKind
    status: JournalStatus
    date: date
    idempotency_key: uuid.UUID
    created_at: datetime
    note: str | None = None
    voided_journal_id: uuid.UUID | None = None


@dataclass(frozen=True, slots=True)
class JournalLine:
    id: uuid.UUID
    journal_id: uuid.UUID
    direction: LineDirection
    amount: Decimal
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    is_external: bool = False
