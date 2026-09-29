import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.services.account_service import AccountService, AccountValidationError


class FakeAccounts:
    def __init__(self) -> None:
        self.items: list[SimpleNamespace] = []

    def create(self, *, name: str, account_type: str) -> SimpleNamespace:
        account = SimpleNamespace(id=uuid.uuid4(), name=name, type=account_type, status="ACTIVE", version=1)
        self.items.append(account)
        return account

    def list(self) -> list[SimpleNamespace]:
        return self.items

    def get_by_id(self, account_id: uuid.UUID):
        return next((item for item in self.items if item.id == account_id), None)

    def update(self, account_id: uuid.UUID, *, name=None, status=None):
        account = self.get_by_id(account_id)
        if account and name is not None:
            account.name = name
        if account and status is not None:
            account.status = status
        return account

    def get_balance(self, account_id: uuid.UUID):
        return Decimal("0.00") if self.get_by_id(account_id) else None


class FakeJournals:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def insert_journal(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), **kwargs)


class FixedClock:
    def today(self) -> date:
        return date(2026, 9, 23)


def test_create_account_rejects_negative_opening_balance() -> None:
    service = AccountService(FakeAccounts(), FakeJournals(), FixedClock())

    with pytest.raises(AccountValidationError, match="negativo"):
        service.create_account(
            name="Banco",
            account_type="BANK",
            opening_balance="-1.00",
            idempotency_key=uuid.uuid4(),
        )


def test_create_account_generates_balanced_opening_journal() -> None:
    accounts = FakeAccounts()
    journals = FakeJournals()
    service = AccountService(accounts, journals, FixedClock())

    account = service.create_account(
        name="Banco Principal",
        account_type="BANK",
        opening_balance="1000.00",
        idempotency_key=uuid.uuid4(),
    )

    assert account.name == "Banco Principal"
    call = journals.calls[0]
    assert call["kind"] == "OPENING"
    assert call["accounting_date"] == date(2026, 9, 23)
    assert len(call["lines"]) == 2
    debit = sum(line.amount for line in call["lines"] if line.direction == "DEBIT")
    credit = sum(line.amount for line in call["lines"] if line.direction == "CREDIT")
    assert debit == credit == Decimal("1000.00")
    assert {line.is_external for line in call["lines"]} == {False, True}


def test_create_zero_balance_account_without_opening_journal() -> None:
    journals = FakeJournals()
    service = AccountService(FakeAccounts(), journals, FixedClock())

    service.create_account(
        name="Efectivo",
        account_type="CASH",
        opening_balance="0.00",
        idempotency_key=uuid.uuid4(),
    )

    assert journals.calls == []


def test_list_accounts_includes_derived_balance() -> None:
    accounts = FakeAccounts()
    account = accounts.create(name="Cash", account_type="CASH")
    service = AccountService(accounts, FakeJournals(), FixedClock())

    result = service.list_accounts()

    assert result == [(account, Decimal("0.00"))]


def test_rename_account_does_not_create_journal() -> None:
    accounts = FakeAccounts()
    journals = FakeJournals()
    account = accounts.create(name="Cash", account_type="CASH")
    service = AccountService(accounts, journals, FixedClock())

    renamed = service.rename_account(account.id, "Efectivo")

    assert renamed.name == "Efectivo"
    assert journals.calls == []


def test_deactivate_account_changes_status_and_missing_account_fails() -> None:
    accounts = FakeAccounts()
    account = accounts.create(name="Cash", account_type="CASH")
    service = AccountService(accounts, FakeJournals(), FixedClock())

    assert service.deactivate_account(account.id).status == "INACTIVE"
    with pytest.raises(AccountValidationError, match="no existe"):
        service.deactivate_account(uuid.uuid4())
