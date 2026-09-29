from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from app.domain.errors import DomainValidationError, ResourceNotFoundError
from app.domain.money import MoneyError, parse_money
from app.domain.ports import JournalLineInput


class AccountValidationError(DomainValidationError):
    pass


class AccountNotFoundError(AccountValidationError, ResourceNotFoundError):
    pass


class AccountStore(Protocol):
    def create(self, *, name: str, account_type: str) -> Any: ...
    def list(self) -> list[Any]: ...
    def get_by_id(self, account_id: uuid.UUID) -> Any | None: ...
    def update(self, account_id: uuid.UUID, *, name: str | None = None, status: str | None = None) -> Any | None: ...
    def get_balance(self, account_id: uuid.UUID) -> Decimal | None: ...


class JournalStore(Protocol):
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


class DateClock(Protocol):
    def today(self) -> date: ...


class AccountService:
    def __init__(self, accounts: AccountStore, journals: JournalStore, clock: DateClock) -> None:
        self._accounts = accounts
        self._journals = journals
        self._clock = clock

    def create_account(
        self,
        *,
        name: str,
        account_type: str,
        opening_balance: str | Decimal,
        idempotency_key: uuid.UUID,
    ) -> Any:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 60:
            raise AccountValidationError("El nombre de la cuenta no es válido", field="name")
        if account_type not in {"CASH", "BANK"}:
            raise AccountValidationError("El tipo de cuenta no es válido", field="type")
        try:
            amount = parse_money(opening_balance, allow_zero=True)
        except MoneyError as error:
            message = "El saldo inicial no puede ser negativo" if str(opening_balance).startswith("-") else str(error)
            raise AccountValidationError(message, field="opening_balance") from error

        account = self._accounts.create(name=normalized_name, account_type=account_type)
        if amount > 0:
            self._journals.insert_journal(
                kind="OPENING",
                accounting_date=self._clock.today(),
                idempotency_key=idempotency_key,
                lines=(
                    JournalLineInput(account_id=account.id, direction="DEBIT", amount=amount),
                    JournalLineInput(is_external=True, direction="CREDIT", amount=amount),
                ),
            )
        return account

    def list_accounts(self) -> list[tuple[Any, Decimal]]:
        result: list[tuple[Any, Decimal]] = []
        for account in self._accounts.list():
            balance = self._accounts.get_balance(account.id)
            if balance is None:
                raise AccountNotFoundError("La cuenta no existe", field="account_id")
            result.append((account, balance))
        return result

    def rename_account(self, account_id: uuid.UUID, name: str) -> Any:
        normalized_name = name.strip()
        if not normalized_name or len(normalized_name) > 60:
            raise AccountValidationError("El nombre de la cuenta no es válido", field="name")
        account = self._accounts.update(account_id, name=normalized_name)
        if account is None:
            raise AccountNotFoundError("La cuenta no existe", field="account_id")
        return account

    def deactivate_account(self, account_id: uuid.UUID) -> Any:
        account = self._accounts.update(account_id, status="INACTIVE")
        if account is None:
            raise AccountNotFoundError("La cuenta no existe", field="account_id")
        return account
