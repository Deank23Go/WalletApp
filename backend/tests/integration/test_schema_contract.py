import os
import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Account, Category, Journal, JournalLine, User

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def create_user(session: Session, email: str) -> User:
    user = User(email=email, password_hash="hash")
    session.add(user)
    session.flush()
    return user


def create_account(session: Session, user: User, name: str = "Cash") -> Account:
    account = Account(user_id=user.id, name=name, type="CASH")
    session.add(account)
    session.flush()
    return account


def create_category(session: Session, user: User, name: str = "Salary") -> Category:
    category = Category(user_id=user.id, name=name, type="INCOME")
    session.add(category)
    session.flush()
    return category


def test_seven_enum_types_and_values_exist(db_engine: Engine) -> None:
    expected = {
        "account_type": ["CASH", "BANK"],
        "account_status": ["ACTIVE", "INACTIVE"],
        "category_type": ["INCOME", "EXPENSE"],
        "category_status": ["ACTIVE", "INACTIVE"],
        "journal_kind": ["OPENING", "INCOME", "EXPENSE", "VOID"],
        "journal_status": ["POSTED", "VOIDED"],
        "line_direction": ["DEBIT", "CREDIT"],
    }
    query = text(
        "SELECT t.typname, array_agg(e.enumlabel ORDER BY e.enumsortorder) "
        "FROM pg_type t JOIN pg_enum e ON e.enumtypid=t.oid "
        "WHERE t.typname = ANY(:names) GROUP BY t.typname"
    )
    with db_engine.connect() as connection:
        actual = {name: list(values) for name, values in connection.execute(query, {"names": list(expected)})}
    assert actual == expected


def test_users_accounts_categories_constraints(db_session: Session) -> None:
    first = create_user(db_session, "first@example.com")
    second = create_user(db_session, "second@example.com")
    first_account = create_account(db_session, first)
    second_account = create_account(db_session, second)
    assert first_account.name == second_account.name
    assert first.preferred_currency == "COP"
    assert first.id is not None
    assert first.created_at is not None

    db_session.add(Account(user_id=first.id, name="   ", type="CASH"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_journal_line_requires_exactly_one_reference(db_session: Session) -> None:
    user = create_user(db_session, "lines@example.com")
    create_account(db_session, user)
    create_category(db_session, user)
    journal = Journal(
        user_id=user.id,
        kind="INCOME",
        date=date.today(),
        idempotency_key=uuid.uuid4(),
    )
    db_session.add(journal)
    db_session.flush()

    invalid = JournalLine(
        journal_id=journal.id,
        account_id=None,
        category_id=None,
        is_external=False,
        direction="DEBIT",
        amount=Decimal("1.00"),
    )
    db_session.add(invalid)
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    user = create_user(db_session, "external@example.com")
    journal = Journal(
        user_id=user.id,
        kind="OPENING",
        date=date.today(),
        idempotency_key=uuid.uuid4(),
    )
    db_session.add(journal)
    db_session.flush()
    db_session.add(
        JournalLine(
            journal_id=journal.id,
            is_external=True,
            direction="CREDIT",
            amount=Decimal("1.00"),
        )
    )
    db_session.flush()


def test_journal_idempotency_is_scoped_by_user(db_session: Session) -> None:
    first = create_user(db_session, "idem-one@example.com")
    second = create_user(db_session, "idem-two@example.com")
    key = uuid.uuid4()
    db_session.add_all(
        [
            Journal(user_id=first.id, kind="OPENING", date=date.today(), idempotency_key=key),
            Journal(user_id=second.id, kind="OPENING", date=date.today(), idempotency_key=key),
        ]
    )
    db_session.flush()


def test_journal_and_lines_are_immutable(db_session: Session) -> None:
    user = create_user(db_session, "immutable@example.com")
    account = create_account(db_session, user)
    journal = Journal(
        user_id=user.id,
        kind="OPENING",
        date=date.today(),
        idempotency_key=uuid.uuid4(),
    )
    db_session.add(journal)
    db_session.flush()
    line = JournalLine(
        journal_id=journal.id,
        account_id=account.id,
        direction="DEBIT",
        amount=Decimal("10.00"),
    )
    db_session.add(line)
    db_session.flush()

    with pytest.raises(DBAPIError):
        db_session.execute(text("UPDATE journals SET user_id=:user_id WHERE id=:id"), {"user_id": uuid.uuid4(), "id": journal.id})
    db_session.rollback()


def test_only_posted_to_voided_transition_is_allowed(db_session: Session) -> None:
    user = create_user(db_session, "status@example.com")
    journal = Journal(
        user_id=user.id,
        kind="INCOME",
        date=date.today(),
        idempotency_key=uuid.uuid4(),
    )
    db_session.add(journal)
    db_session.flush()
    db_session.execute(text("UPDATE journals SET status='VOIDED' WHERE id=:id"), {"id": journal.id})
    db_session.flush()
    with pytest.raises(DBAPIError):
        db_session.execute(text("UPDATE journals SET status='POSTED' WHERE id=:id"), {"id": journal.id})
    db_session.rollback()


def test_required_indexes_exist(db_engine: Engine) -> None:
    inspector = inspect(db_engine)
    expected = {
        "accounts": {"ix_accounts_user_id"},
        "categories": {"ix_categories_user"},
        "journals": {"ix_journals_user_date"},
        "journal_lines": {"ix_lines_journal", "ix_lines_account", "ix_lines_category"},
        "refresh_tokens": {"ix_refresh_user"},
    }
    for table, names in expected.items():
        actual = {index["name"] for index in inspector.get_indexes(table)}
        assert names <= actual


def test_alembic_has_no_model_drift(test_database_url: str, db_engine: Engine) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=BACKEND_ROOT,
        env=os.environ | {"DATABASE_URL": test_database_url, "JWT_SECRET": "test-secret"},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "No new upgrade operations detected" in result.stdout
