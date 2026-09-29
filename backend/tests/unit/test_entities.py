import uuid
from dataclasses import FrozenInstanceError
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.domain.entities import Account, Category, Journal, JournalLine, User


def test_journal_line_preserves_decimal_amount_exactly() -> None:
    amount = Decimal("150000.00")
    line = JournalLine(
        id=uuid.uuid4(),
        journal_id=uuid.uuid4(),
        direction="DEBIT",
        amount=amount,
        account_id=uuid.uuid4(),
    )

    assert line.amount == amount
    assert line.amount.as_tuple() == amount.as_tuple()
    assert isinstance(line.amount, Decimal)


def test_domain_entities_preserve_financial_relationships() -> None:
    user_id = uuid.uuid4()
    account_id = uuid.uuid4()
    category_id = uuid.uuid4()
    journal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    user = User(id=user_id, email="ana@example.com", preferred_currency="COP", created_at=now)
    account = Account(
        id=account_id,
        user_id=user_id,
        name="Banco Principal",
        type="BANK",
        status="ACTIVE",
        version=1,
        created_at=now,
        updated_at=now,
    )
    category = Category(
        id=category_id,
        user_id=user_id,
        name="Salario",
        type="INCOME",
        is_seed=True,
        status="ACTIVE",
        created_at=now,
    )
    journal = Journal(
        id=journal_id,
        user_id=user_id,
        kind="INCOME",
        status="POSTED",
        date=date.today(),
        idempotency_key=uuid.uuid4(),
        created_at=now,
    )

    assert account.user_id == user.id
    assert category.user_id == user.id
    assert journal.user_id == user.id


def test_domain_entities_are_immutable() -> None:
    user = User(
        id=uuid.uuid4(),
        email="ana@example.com",
        preferred_currency="COP",
        created_at=datetime.now(timezone.utc),
    )

    with pytest.raises(FrozenInstanceError):
        user.email = "changed@example.com"
