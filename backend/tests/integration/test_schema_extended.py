import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Account, Journal, JournalLine, RefreshToken, User


def user(session: Session, email: str) -> User:
    item = User(email=email, password_hash="hash")
    session.add(item)
    session.flush()
    return item


def test_user_constraints_reject_invalid_email_currency_and_duplicates(db_session: Session) -> None:
    db_session.add(User(email="valid@example.com", password_hash="hash"))
    db_session.flush()
    db_session.add(User(email="valid@example.com", password_hash="hash"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    db_session.add(User(email="invalid", password_hash="hash"))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()

    db_session.add(User(email="currency@example.com", password_hash="hash", preferred_currency="peso"))
    with pytest.raises(DBAPIError):
        db_session.flush()
    db_session.rollback()


def test_refresh_token_constraints_and_cascade(db_session: Session) -> None:
    owner = user(db_session, "refresh@example.com")
    token = RefreshToken(
        user_id=owner.id,
        token_hash="unique-hash",
        family_id=uuid.uuid4(),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db_session.add(token)
    db_session.flush()
    assert token.id is not None
    assert token.created_at is not None
    db_session.delete(owner)
    db_session.flush()
    assert db_session.get(RefreshToken, token.id) is None


def test_all_ledger_mutations_except_void_transition_are_rejected(db_session: Session) -> None:
    owner = user(db_session, "ledger@example.com")
    account = Account(user_id=owner.id, name="Cash", type="CASH")
    db_session.add(account)
    db_session.flush()
    journal = Journal(user_id=owner.id, kind="OPENING", date=date.today(), idempotency_key=uuid.uuid4())
    db_session.add(journal)
    db_session.flush()
    line = JournalLine(journal_id=journal.id, account_id=account.id, direction="DEBIT", amount=Decimal("1.00"))
    db_session.add(line)
    db_session.flush()

    for statement in (
        update(Journal).where(Journal.id == journal.id).values(note="changed"),
        delete(Journal).where(Journal.id == journal.id),
        update(JournalLine).where(JournalLine.id == line.id).values(amount=Decimal("2.00")),
        delete(JournalLine).where(JournalLine.id == line.id),
    ):
        nested = db_session.begin_nested()
        with pytest.raises(DBAPIError):
            db_session.execute(statement)
        nested.rollback()


def test_journal_index_has_descending_date_order(db_engine: Engine) -> None:
    with db_engine.connect() as connection:
        definition = connection.scalar(
            text("SELECT pg_get_indexdef(indexrelid) FROM pg_index WHERE indexrelid='ix_journals_user_date'::regclass")
        )
    normalized = definition.upper()
    assert "DATE DESC" in normalized
    assert "CREATED_AT DESC" in normalized
