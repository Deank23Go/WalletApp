import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.errors import ConcurrencyError, DomainValidationError
from app.domain.ports import StoredResponse
from app.domain.services.movement_service import MovementService, movement_lines, validate_movement

TODAY = date(2026, 9, 28)


def valid_values():
    return {
        "movement_type": "EXPENSE",
        "amount": "10.00",
        "accounting_date": TODAY,
        "today": TODAY,
        "account": SimpleNamespace(status="ACTIVE"),
        "category": SimpleNamespace(status="ACTIVE", type="EXPENSE"),
        "available_balance": Decimal("10.00"),
        "note": None,
    }


@pytest.mark.parametrize("amount", ["0", "-1", "0.001", "10.999"])
def test_movement_rules_reject_invalid_amounts(amount: str) -> None:
    values = valid_values() | {"amount": amount}
    with pytest.raises(DomainValidationError):
        validate_movement(**values)


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"accounting_date": TODAY + timedelta(days=1)}, "date"),
        ({"account": SimpleNamespace(status="INACTIVE")}, "account_id"),
        ({"category": SimpleNamespace(status="INACTIVE", type="EXPENSE")}, "category_id"),
        ({"category": SimpleNamespace(status="ACTIVE", type="INCOME")}, "category_id"),
        ({"available_balance": Decimal("9.99")}, "amount"),
        ({"note": "x" * 256}, "note"),
    ],
)
def test_movement_rules_reject_business_violations(override: dict, field: str) -> None:
    values = valid_values() | override
    with pytest.raises(DomainValidationError) as error:
        validate_movement(**values)
    assert error.value.field == field


def test_movement_rules_accept_exact_expense_balance_and_build_balanced_lines() -> None:
    amount = validate_movement(**valid_values())
    expense = movement_lines(
        movement_type="EXPENSE",
        account_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        amount=amount,
    )
    income = movement_lines(
        movement_type="INCOME",
        account_id=uuid.uuid4(),
        category_id=uuid.uuid4(),
        amount=amount,
    )

    assert [line.direction for line in expense] == ["CREDIT", "DEBIT"]
    assert [line.direction for line in income] == ["DEBIT", "CREDIT"]
    assert sum(line.amount for line in expense if line.direction == "DEBIT") == sum(
        line.amount for line in expense if line.direction == "CREDIT"
    )


@pytest.mark.parametrize(
    ("movement_type", "amount", "accounting_date", "available_balance"),
    [
        ("INCOME", "0.01", TODAY - timedelta(days=1), Decimal("0.00")),
        ("INCOME", "99999999999999999.99", TODAY, Decimal("0.00")),
        ("EXPENSE", "10.00", TODAY, Decimal("10.00")),
    ],
)
def test_movement_rules_accept_valid_boundaries(
    movement_type: str,
    amount: str,
    accounting_date: date,
    available_balance: Decimal,
) -> None:
    category = SimpleNamespace(status="ACTIVE", type=movement_type)
    assert validate_movement(
        movement_type=movement_type,
        amount=amount,
        accounting_date=accounting_date,
        today=TODAY,
        account=SimpleNamespace(status="ACTIVE"),
        category=category,
        available_balance=available_balance,
        note=None,
    ) == Decimal(amount)


class FakeAccounts:
    def __init__(self) -> None:
        self.account = SimpleNamespace(id=uuid.uuid4(), status="ACTIVE", version=1)
        self.balance = Decimal("100.00")
        self.bump_count = 0

    def get_for_update(self, account_id):
        return self.account if account_id == self.account.id else None

    def get_balance(self, account_id):
        return self.balance if account_id == self.account.id else None

    def bump_version(self, account_id, expected_version):
        self.bump_count += 1
        return 1


class FakeCategories:
    def __init__(self) -> None:
        self.category = SimpleNamespace(id=uuid.uuid4(), status="ACTIVE", type="EXPENSE")

    def get_by_id(self, category_id):
        return self.category if category_id == self.category.id else None


class FakeJournals:
    def __init__(self) -> None:
        self.calls = []

    def insert_journal(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=uuid.uuid4(), status="POSTED")


class FakeResponses:
    def __init__(self) -> None:
        self.pending = set()
        self.completed = {}

    def claim(self, key):
        if key in self.pending or key in self.completed:
            return False
        self.pending.add(key)
        return True

    def complete(self, key, *, status_code, body):
        self.pending.remove(key)
        self.completed[key] = StoredResponse(status_code=status_code, body=body)
        return True

    def load(self, key):
        return self.completed.get(key)


class FixedClock:
    def today(self):
        return TODAY


def test_record_movement_replays_same_idempotency_key_without_duplicate() -> None:
    accounts = FakeAccounts()
    categories = FakeCategories()
    journals = FakeJournals()
    responses = FakeResponses()
    service = MovementService(accounts, categories, journals, responses, FixedClock())
    key = uuid.uuid4()
    request = {
        "movement_type": "EXPENSE",
        "account_id": accounts.account.id,
        "category_id": categories.category.id,
        "amount": "25.00",
        "accounting_date": TODAY,
        "note": "Mercado",
        "idempotency_key": key,
    }

    first = service.record_movement(**request)
    replay = service.record_movement(**request)

    assert first.body == replay.body
    assert replay.replayed is True
    assert len(journals.calls) == 1
    assert accounts.bump_count == 1
    assert first.body["new_balance"] == "75.00"


def test_record_movement_rejects_stale_account_version() -> None:
    accounts = FakeAccounts()
    accounts.bump_version = lambda account_id, expected_version: 0
    categories = FakeCategories()
    service = MovementService(accounts, categories, FakeJournals(), FakeResponses(), FixedClock())

    with pytest.raises(ConcurrencyError, match="Conflicto de concurrencia"):
        service.record_movement(
            movement_type="EXPENSE",
            account_id=accounts.account.id,
            category_id=categories.category.id,
            amount="25.00",
            accounting_date=TODAY,
            note=None,
            idempotency_key=uuid.uuid4(),
        )
