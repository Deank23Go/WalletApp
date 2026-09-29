from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from app.domain.errors import ConcurrencyError, DomainValidationError, ResourceNotFoundError
from app.domain.ports import Direction, JournalLineInput


class AccountStore(Protocol):
    def get_for_update(self, account_id: uuid.UUID) -> Any | None: ...


class JournalStore(Protocol):
    def get_by_id(self, journal_id: uuid.UUID) -> Any | None: ...
    def get_account_line(self, journal_id: uuid.UUID) -> Any: ...
    def void_journal(
        self,
        original_id: uuid.UUID,
        *,
        idempotency_key: uuid.UUID,
        account_id: uuid.UUID,
        account_version: int,
        accounting_date: date,
    ) -> Any: ...
    def balance_query(self, account_id: uuid.UUID) -> Decimal | None: ...


class DateClock(Protocol):
    def today(self) -> date: ...


@dataclass(frozen=True)
class VoidResult:
    journal: Any
    new_balance: Decimal
    negative_balance_warning: bool


def opposite_direction(direction: Direction) -> Direction:
    return "CREDIT" if direction == "DEBIT" else "DEBIT"


def invert_lines(lines: list[Any]) -> tuple[JournalLineInput, JournalLineInput]:
    if len(lines) != 2:
        raise DomainValidationError("El movimiento debe contener exactamente dos líneas")
    mirrored = tuple(
        JournalLineInput(
            account_id=line.account_id,
            category_id=line.category_id,
            is_external=line.is_external,
            direction=opposite_direction(line.direction),
            amount=line.amount,
        )
        for line in lines
    )
    return mirrored[0], mirrored[1]


class VoidService:
    def __init__(self, accounts: AccountStore, journals: JournalStore, clock: DateClock) -> None:
        self._accounts = accounts
        self._journals = journals
        self._clock = clock

    def void_movement(self, movement_id: uuid.UUID) -> VoidResult:
        original = self._journals.get_by_id(movement_id)
        if original is None or original.kind == "VOID":
            raise ResourceNotFoundError("El movimiento no existe", field="movement_id")
        if original.status == "VOIDED":
            raise DomainValidationError("El movimiento ya está anulado", field="movement_id")
        invert_lines(list(original.lines))
        account_line = self._journals.get_account_line(movement_id)
        account = self._accounts.get_for_update(account_line.account_id)
        if account is None:
            raise ResourceNotFoundError("La cuenta no existe", field="account_id")
        try:
            void_journal = self._journals.void_journal(
                movement_id,
                idempotency_key=uuid.uuid4(),
                account_id=account.id,
                account_version=account.version,
                accounting_date=self._clock.today(),
            )
        except RuntimeError as error:
            raise ConcurrencyError("Conflicto de concurrencia, reintente la operación") from error
        except ValueError as error:
            raise DomainValidationError("El movimiento ya está anulado", field="movement_id") from error
        new_balance = self._journals.balance_query(account.id)
        if new_balance is None:
            raise ResourceNotFoundError("La cuenta no existe", field="account_id")
        return VoidResult(
            journal=void_journal,
            new_balance=new_balance,
            negative_balance_warning=new_balance < 0,
        )
