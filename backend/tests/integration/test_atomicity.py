from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import SystemClock
from app.db.models import Account, Journal, JournalLine, JournalResponse
from app.db.session import SqlAlchemyUnitOfWork
from app.domain.services.account_service import AccountService
from app.domain.services.movement_service import MovementService
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.repositories.journals_repo import SqlJournalRepository
from app.repositories.users_repo import SqlUserRepository


class FailingJournalRepository(SqlJournalRepository):
    def insert_journal(self, **kwargs):
        journal = super().insert_journal(**kwargs)
        raise RuntimeError(f"forced failure after journal {journal.id}")


def test_movement_failure_after_journal_flush_rolls_back_everything(
    committed_session_factory: sessionmaker[Session],
) -> None:
    with committed_session_factory.begin() as session:
        user = SqlUserRepository(session).create(email="atomic-movement@example.com", password_hash="hash")
        account = SqlAccountRepository(session, user.id).create(name="Cash", account_type="CASH")
        category = SqlCategoryRepository(session, user.id).create(name="Salary", category_type="INCOME")
        user_id = user.id
        account_id = account.id
        category_id = category.id
        initial_version = account.version

    key = uuid.uuid4()
    uow = SqlAlchemyUnitOfWork(committed_session_factory)
    with pytest.raises(RuntimeError, match="forced failure"):
        MovementService(
            SqlAccountRepository(uow.session, user_id),
            SqlCategoryRepository(uow.session, user_id),
            FailingJournalRepository(uow.session, user_id),
            SqlJournalResponseRepository(uow.session, user_id),
            SystemClock(),
        ).record_movement(
            movement_type="INCOME",
            account_id=account_id,
            category_id=category_id,
            amount="10.00",
            accounting_date=date.today(),
            note=None,
            idempotency_key=key,
        )
    uow.rollback()
    uow.close()

    with committed_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Journal)) == 0
        assert session.scalar(select(func.count()).select_from(JournalLine)) == 0
        assert session.scalar(select(func.count()).select_from(JournalResponse)) == 0
        persisted_account = session.get(Account, account_id)
        assert persisted_account is not None
        assert persisted_account.version == initial_version
        assert SqlAccountRepository(session, user_id).get_balance(account_id) == Decimal("0.00")


def test_opening_failure_rolls_back_account_and_opening_journal(
    committed_session_factory: sessionmaker[Session],
) -> None:
    with committed_session_factory.begin() as session:
        user_id = SqlUserRepository(session).create(
            email="atomic-account@example.com",
            password_hash="hash",
        ).id

    uow = SqlAlchemyUnitOfWork(committed_session_factory)
    with pytest.raises(RuntimeError, match="forced failure"):
        AccountService(
            SqlAccountRepository(uow.session, user_id),
            FailingJournalRepository(uow.session, user_id),
            SystemClock(),
        ).create_account(
            name="Bank",
            account_type="BANK",
            opening_balance="100.00",
            idempotency_key=uuid.uuid4(),
        )
    uow.rollback()
    uow.close()

    with committed_session_factory() as session:
        assert session.scalar(select(func.count()).select_from(Account)) == 0
        assert session.scalar(select(func.count()).select_from(Journal)) == 0
        assert session.scalar(select(func.count()).select_from(JournalLine)) == 0
