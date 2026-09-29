from __future__ import annotations

import threading
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.security import SystemClock
from app.db.models import Account, Journal, JournalResponse
from app.db.session import SqlAlchemyUnitOfWork
from app.domain.errors import DomainConflictError, DomainValidationError
from app.domain.services.account_service import AccountService
from app.domain.services.movement_service import MovementService
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.repositories.journals_repo import SqlJournalRepository
from app.repositories.users_repo import SqlUserRepository


def test_two_concurrent_expenses_cannot_overspend(
    committed_session_factory: sessionmaker[Session],
) -> None:
    with committed_session_factory.begin() as session:
        user = SqlUserRepository(session).create(email="concurrent-spend@example.com", password_hash="hash")
        accounts = SqlAccountRepository(session, user.id)
        account = AccountService(accounts, SqlJournalRepository(session, user.id), SystemClock()).create_account(
            name="Cash",
            account_type="CASH",
            opening_balance="100.00",
            idempotency_key=uuid.uuid4(),
        )
        category = SqlCategoryRepository(session, user.id).create(name="Market", category_type="EXPENSE")
        user_id = user.id
        account_id = account.id
        category_id = category.id

    barrier = threading.Barrier(2)
    outcomes: list[int] = []
    errors: list[BaseException] = []
    lock = threading.Lock()

    def spend() -> None:
        uow = SqlAlchemyUnitOfWork(committed_session_factory)
        try:
            barrier.wait(timeout=5)
            MovementService(
                SqlAccountRepository(uow.session, user_id),
                SqlCategoryRepository(uow.session, user_id),
                SqlJournalRepository(uow.session, user_id),
                SqlJournalResponseRepository(uow.session, user_id),
                SystemClock(),
            ).record_movement(
                movement_type="EXPENSE",
                account_id=account_id,
                category_id=category_id,
                amount="80.00",
                accounting_date=date.today(),
                note=None,
                idempotency_key=uuid.uuid4(),
            )
            uow.commit()
            with lock:
                outcomes.append(201)
        except DomainValidationError:
            uow.rollback()
            with lock:
                outcomes.append(422)
        except DomainConflictError:
            uow.rollback()
            with lock:
                outcomes.append(409)
        except BaseException as error:
            uow.rollback()
            with lock:
                errors.append(error)
        finally:
            uow.close()

    workers = [threading.Thread(target=spend) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    assert all(not worker.is_alive() for worker in workers)
    assert errors == []
    assert sorted(outcomes) in ([201, 409], [201, 422])
    with committed_session_factory() as session:
        account = session.get(Account, account_id)
        assert account is not None
        assert account.version == 2
        assert SqlAccountRepository(session, user_id).get_balance(account_id) == Decimal("20.00")
        assert session.scalar(
            select(func.count()).select_from(Journal).where(Journal.user_id == user_id, Journal.kind == "EXPENSE")
        ) == 1
        assert session.scalar(
            select(func.count()).select_from(JournalResponse).where(JournalResponse.state == "PENDING")
        ) == 0
