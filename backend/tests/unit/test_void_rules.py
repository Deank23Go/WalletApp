import uuid
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domain.errors import DomainValidationError
from app.domain.services.void_service import VoidService, invert_lines


def line(direction, *, account=False, category=False):
    return SimpleNamespace(
        account_id=uuid.uuid4() if account else None,
        category_id=uuid.uuid4() if category else None,
        is_external=not account and not category,
        direction=direction,
        amount=Decimal("10.00"),
    )


def test_invert_lines_preserves_references_amounts_and_reverses_directions() -> None:
    original = [line("DEBIT", account=True), line("CREDIT", category=True)]

    mirrored = invert_lines(original)

    assert [item.direction for item in mirrored] == ["CREDIT", "DEBIT"]
    assert [item.amount for item in mirrored] == [Decimal("10.00"), Decimal("10.00")]
    assert mirrored[0].account_id == original[0].account_id
    assert mirrored[1].category_id == original[1].category_id


class FakeAccounts:
    def __init__(self, account):
        self.account = account

    def get_for_update(self, account_id):
        return self.account if account_id == self.account.id else None


class FakeJournals:
    def __init__(self, account, *, status="POSTED", balance=Decimal("-5.00")):
        self.original = SimpleNamespace(
            id=uuid.uuid4(),
            kind="INCOME",
            status=status,
            lines=[line("DEBIT", account=True), line("CREDIT", category=True)],
        )
        self.original.lines[0].account_id = account.id
        self.balance = balance

    def get_by_id(self, journal_id):
        return self.original if journal_id == self.original.id else None

    def get_account_line(self, journal_id):
        return self.original.lines[0]

    def void_journal(self, original_id, **kwargs):
        return SimpleNamespace(id=uuid.uuid4(), kind="VOID", status="POSTED", date=date(2026, 9, 28))

    def balance_query(self, account_id):
        return self.balance


class FixedClock:
    def today(self):
        return date(2026, 9, 28)


def test_void_service_returns_negative_balance_warning() -> None:
    account = SimpleNamespace(id=uuid.uuid4(), version=2)
    journals = FakeJournals(account)
    result = VoidService(FakeAccounts(account), journals, FixedClock()).void_movement(journals.original.id)

    assert result.new_balance == Decimal("-5.00")
    assert result.negative_balance_warning is True


def test_void_service_rejects_already_voided_movement() -> None:
    account = SimpleNamespace(id=uuid.uuid4(), version=2)
    journals = FakeJournals(account, status="VOIDED")

    with pytest.raises(DomainValidationError, match="ya está anulado"):
        VoidService(FakeAccounts(account), journals, FixedClock()).void_movement(journals.original.id)
