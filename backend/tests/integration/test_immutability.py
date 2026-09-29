from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import delete, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.db.models import Account, Journal, JournalLine, User


def _ledger(session: Session) -> tuple[Journal, JournalLine]:
    user = User(email="immutability@example.com", password_hash="hash")
    session.add(user)
    session.flush()
    account = Account(user_id=user.id, name="Cash", type="CASH")
    session.add(account)
    session.flush()
    journal = Journal(
        user_id=user.id,
        kind="OPENING",
        date=date.today(),
        idempotency_key=uuid.uuid4(),
    )
    session.add(journal)
    session.flush()
    line = JournalLine(
        journal_id=journal.id,
        account_id=account.id,
        direction="DEBIT",
        amount=Decimal("1.00"),
    )
    session.add(line)
    session.flush()
    return journal, line


def test_five_ledger_mutations_are_rejected_and_void_transition_is_allowed(db_session: Session) -> None:
    journal, line = _ledger(db_session)
    forbidden = (
        update(Journal).where(Journal.id == journal.id).values(note="changed"),
        update(Journal).where(Journal.id == journal.id).values(date=date(2020, 1, 1)),
        delete(Journal).where(Journal.id == journal.id),
        update(JournalLine).where(JournalLine.id == line.id).values(amount=Decimal("2.00")),
        delete(JournalLine).where(JournalLine.id == line.id),
    )

    for statement in forbidden:
        nested = db_session.begin_nested()
        with pytest.raises(DBAPIError):
            db_session.execute(statement)
        nested.rollback()

    db_session.execute(
        text("UPDATE journals SET status='VOIDED' WHERE id=:journal_id"),
        {"journal_id": journal.id},
    )
    db_session.flush()
    db_session.expire(journal)
    assert db_session.get(Journal, journal.id).status == "VOIDED"
