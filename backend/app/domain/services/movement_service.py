from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Protocol

from app.domain.errors import (
    ConcurrencyError,
    DomainConflictError,
    DomainValidationError,
    IdempotencyError,
    ResourceNotFoundError,
)
from app.domain.money import MoneyError, parse_money
from app.domain.ports import JournalLineInput, JsonObject, StoredResponse


class AccountStore(Protocol):
    def get_for_update(self, account_id: uuid.UUID) -> Any | None: ...
    def bump_version(self, account_id: uuid.UUID, expected_version: int) -> int: ...
    def get_balance(self, account_id: uuid.UUID) -> Decimal | None: ...


class CategoryStore(Protocol):
    def get_by_id(self, category_id: uuid.UUID) -> Any | None: ...


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


class ResponseStore(Protocol):
    def claim(self, idempotency_key: uuid.UUID) -> bool: ...
    def complete(self, idempotency_key: uuid.UUID, *, status_code: int, body: JsonObject) -> bool: ...
    def load(self, idempotency_key: uuid.UUID) -> StoredResponse | None: ...


class DateClock(Protocol):
    def today(self) -> date: ...


@dataclass(frozen=True)
class MovementResult:
    status_code: int
    body: JsonObject
    replayed: bool = False


def validate_movement(
    *,
    movement_type: str,
    amount: str | Decimal,
    accounting_date: date,
    today: date,
    account: Any,
    category: Any,
    available_balance: Decimal,
    note: str | None,
) -> Decimal:
    if movement_type not in {"INCOME", "EXPENSE"}:
        raise DomainValidationError("El tipo de movimiento no es válido", field="type")
    try:
        parsed_amount = parse_money(amount)
    except MoneyError as error:
        raise DomainValidationError(str(error), field="amount") from error
    if accounting_date > today:
        raise DomainValidationError("La fecha del movimiento no puede ser futura", field="date")
    if note is not None and len(note) > 255:
        raise DomainValidationError("La nota no puede exceder 255 caracteres", field="note")
    if account.status != "ACTIVE":
        raise DomainValidationError("La cuenta está inactiva", field="account_id")
    if category.status != "ACTIVE" or category.type != movement_type:
        raise DomainValidationError("La categoría no es válida para este tipo de movimiento", field="category_id")
    if movement_type == "EXPENSE" and parsed_amount > available_balance:
        raise DomainValidationError(
            f"Saldo insuficiente en la cuenta. Saldo disponible: {available_balance:.2f}",
            field="amount",
        )
    return parsed_amount


def movement_lines(
    *,
    movement_type: str,
    account_id: uuid.UUID,
    category_id: uuid.UUID,
    amount: Decimal,
) -> tuple[JournalLineInput, JournalLineInput]:
    if movement_type == "INCOME":
        return (
            JournalLineInput(account_id=account_id, direction="DEBIT", amount=amount),
            JournalLineInput(category_id=category_id, direction="CREDIT", amount=amount),
        )
    if movement_type == "EXPENSE":
        return (
            JournalLineInput(account_id=account_id, direction="CREDIT", amount=amount),
            JournalLineInput(category_id=category_id, direction="DEBIT", amount=amount),
        )
    raise DomainValidationError("El tipo de movimiento no es válido", field="type")


class MovementService:
    OPERATION = "movement.create"

    def __init__(
        self,
        accounts: AccountStore,
        categories: CategoryStore,
        journals: JournalStore,
        responses: ResponseStore,
        clock: DateClock,
    ) -> None:
        self._accounts = accounts
        self._categories = categories
        self._journals = journals
        self._responses = responses
        self._clock = clock

    def record_movement(
        self,
        *,
        movement_type: str,
        account_id: uuid.UUID,
        category_id: uuid.UUID,
        amount: str | Decimal,
        accounting_date: date,
        note: str | None,
        idempotency_key: uuid.UUID,
    ) -> MovementResult:
        if not self._responses.claim(idempotency_key):
            return self._replay(idempotency_key)

        account = self._accounts.get_for_update(account_id)
        if account is None:
            raise ResourceNotFoundError("La cuenta no existe", field="account_id")
        category = self._categories.get_by_id(category_id)
        if category is None:
            raise DomainValidationError("La categoría no es válida para este tipo de movimiento", field="category_id")
        balance = self._accounts.get_balance(account_id)
        if balance is None:
            raise ResourceNotFoundError("La cuenta no existe", field="account_id")
        parsed_amount = validate_movement(
            movement_type=movement_type,
            amount=amount,
            accounting_date=accounting_date,
            today=self._clock.today(),
            account=account,
            category=category,
            available_balance=balance,
            note=note,
        )
        journal = self._journals.insert_journal(
            kind=movement_type,
            accounting_date=accounting_date,
            idempotency_key=idempotency_key,
            note=note.strip() if note else None,
            lines=movement_lines(
                movement_type=movement_type,
                account_id=account_id,
                category_id=category_id,
                amount=parsed_amount,
            ),
        )
        if self._accounts.bump_version(account_id, account.version) != 1:
            raise ConcurrencyError("Conflicto de concurrencia, reintente la operación")
        new_balance = balance + parsed_amount if movement_type == "INCOME" else balance - parsed_amount
        response_body: JsonObject = {
            "movement": {
                "id": str(journal.id),
                "type": movement_type,
                "status": journal.status,
                "account_id": str(account_id),
                "category_id": str(category_id),
                "amount": f"{parsed_amount:.2f}",
                "date": accounting_date.isoformat(),
                "note": note.strip() if note else None,
            },
            "new_balance": f"{new_balance:.2f}",
        }
        stored_body: JsonObject = {"operation": self.OPERATION, "response": response_body}
        if not self._responses.complete(idempotency_key, status_code=201, body=stored_body):
            raise IdempotencyError("No fue posible completar la operación idempotente")
        return MovementResult(status_code=201, body=response_body)

    def _replay(self, idempotency_key: uuid.UUID) -> MovementResult:
        stored = self._responses.load(idempotency_key)
        if stored is None:
            raise IdempotencyError("La operación con esta clave todavía está en proceso")
        if stored.body.get("operation") != self.OPERATION:
            raise DomainConflictError("La clave de idempotencia ya fue utilizada en otra operación", field="Idempotency-Key")
        response = stored.body.get("response")
        if not isinstance(response, dict):
            raise IdempotencyError("La respuesta idempotente almacenada no es válida")
        return MovementResult(status_code=stored.status_code, body=response, replayed=True)
