from __future__ import annotations

import builtins
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

JsonValue = None | bool | int | str | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject = dict[str, JsonValue]
Direction = Literal["DEBIT", "CREDIT"]


@dataclass(frozen=True)
class JournalLineInput:
    direction: Direction
    amount: Decimal
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    is_external: bool = False


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: JsonObject


@dataclass(frozen=True)
class AccessToken:
    value: str
    expires_in: int


@dataclass(frozen=True)
class RefreshTokenValue:
    plaintext: str
    token_hash: str


class Clock(ABC):
    @abstractmethod
    def today(self) -> date: ...

    @abstractmethod
    def now(self) -> datetime: ...


class PasswordHasher(ABC):
    @abstractmethod
    def hash(self, plaintext: str) -> str: ...

    @abstractmethod
    def verify(self, plaintext: str, hashed: str) -> bool: ...


class AccessTokenCodec(ABC):
    @abstractmethod
    def issue(self, user_id: uuid.UUID) -> AccessToken: ...

    @abstractmethod
    def decode_subject(self, token: str) -> uuid.UUID: ...


class RefreshTokenCodec(ABC):
    @abstractmethod
    def generate(self) -> RefreshTokenValue: ...

    @abstractmethod
    def hash(self, plaintext: str) -> str: ...


class UserRepository(ABC):
    @abstractmethod
    def create(self, *, email: str, password_hash: str, preferred_currency: str = "COP") -> Any: ...

    @abstractmethod
    def get_by_email(self, email: str) -> Any | None: ...

    @abstractmethod
    def get_by_id(self, user_id: uuid.UUID) -> Any | None: ...


class AccountRepository(ABC):
    @abstractmethod
    def create(self, *, name: str, account_type: str) -> Any: ...

    @abstractmethod
    def list(self) -> list[Any]: ...

    @abstractmethod
    def list_with_balances(self, *, status: str | None = None) -> builtins.list[tuple[Any, Decimal]]: ...

    @abstractmethod
    def get_by_id(self, account_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    def get_for_update(self, account_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    def update(self, account_id: uuid.UUID, *, name: str | None = None, status: str | None = None) -> Any | None: ...

    @abstractmethod
    def bump_version(self, account_id: uuid.UUID, expected_version: int) -> int: ...

    @abstractmethod
    def get_balance(self, account_id: uuid.UUID) -> Decimal | None: ...


class CategoryRepository(ABC):
    @abstractmethod
    def create(self, *, name: str, category_type: str, is_seed: bool = False) -> Any: ...

    @abstractmethod
    def list(self, *, category_type: str | None = None, status: str | None = None) -> list[Any]: ...

    @abstractmethod
    def get_by_id(self, category_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    def update(self, category_id: uuid.UUID, *, name: str | None = None, status: str | None = None) -> Any | None: ...

    @abstractmethod
    def clone_seed_catalog(self) -> int: ...


class JournalRepository(ABC):
    @abstractmethod
    def insert_journal(
        self,
        *,
        kind: str,
        accounting_date: date,
        idempotency_key: uuid.UUID,
        lines: tuple[JournalLineInput, JournalLineInput],
        note: str | None = None,
        voided_journal_id: uuid.UUID | None = None,
    ) -> Any: ...

    @abstractmethod
    def get_by_id(self, journal_id: uuid.UUID) -> Any | None: ...

    @abstractmethod
    def list_paginated(
        self,
        *,
        account_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Any], int]: ...

    @abstractmethod
    def balance_query(self, account_id: uuid.UUID) -> Decimal | None: ...

    @abstractmethod
    def get_account_line(self, journal_id: uuid.UUID) -> Any: ...

    @abstractmethod
    def void_journal(
        self,
        original_id: uuid.UUID,
        *,
        idempotency_key: uuid.UUID,
        account_id: uuid.UUID,
        account_version: int,
        accounting_date: date,
    ) -> Any: ...


class JournalResponseRepository(ABC):
    @abstractmethod
    def claim(self, idempotency_key: uuid.UUID) -> bool: ...

    @abstractmethod
    def complete(self, idempotency_key: uuid.UUID, *, status_code: int, body: JsonObject) -> bool: ...

    @abstractmethod
    def load(self, idempotency_key: uuid.UUID) -> StoredResponse | None: ...


class RefreshTokenRepository(ABC):
    @abstractmethod
    def create(
        self,
        *,
        user_id: uuid.UUID,
        token_hash: str,
        family_id: uuid.UUID,
        expires_at: datetime,
    ) -> Any: ...

    @abstractmethod
    def get_by_hash_for_update(self, token_hash: str) -> Any | None: ...

    @abstractmethod
    def revoke(self, token_hash: str, *, revoked_at: datetime) -> bool: ...

    @abstractmethod
    def revoke_family(self, family_id: uuid.UUID, *, revoked_at: datetime) -> int: ...
