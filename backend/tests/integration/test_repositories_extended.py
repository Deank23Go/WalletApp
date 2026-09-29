import threading
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy.orm import Session, sessionmaker

from app.domain.ports import JournalLineInput
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.repositories.journals_repo import SqlJournalRepository
from app.repositories.users_repo import SqlUserRepository


def create_user(session: Session, email: str):
    return SqlUserRepository(session).create(email=email, password_hash="hash")


def test_user_repository_normalizes_and_relies_on_external_transaction(db_session: Session) -> None:
    repository = SqlUserRepository(db_session)
    created = repository.create(email="  NORMALIZED@EXAMPLE.COM ", password_hash="hash")
    assert repository.get_by_email("normalized@example.com").id == created.id
    assert repository.get_by_id(created.id).id == created.id


def test_account_crud_filters_and_zero_balance(db_session: Session) -> None:
    first = create_user(db_session, "accounts-first@example.com")
    second = create_user(db_session, "accounts-second@example.com")
    first_repo = SqlAccountRepository(db_session, first.id)
    second_repo = SqlAccountRepository(db_session, second.id)
    account = first_repo.create(name="Cash", account_type="CASH")
    assert first_repo.list() == [account]
    assert second_repo.list() == []
    assert first_repo.update(account.id, name="Wallet").name == "Wallet"
    assert second_repo.update(account.id, name="Stolen") is None
    assert first_repo.get_for_update(account.id).id == account.id
    assert first_repo.get_balance(account.id) == Decimal("0.00")
    assert first_repo.bump_version(account.id, 999) == 0


def test_category_filters_are_tenant_scoped(db_session: Session) -> None:
    owner = create_user(db_session, "filters@example.com")
    repo = SqlCategoryRepository(db_session, owner.id)
    income = repo.create(name="Salary", category_type="INCOME")
    expense = repo.create(name="Food", category_type="EXPENSE")
    repo.update(expense.id, status="INACTIVE")
    assert repo.list(category_type="INCOME") == [income]
    assert repo.list(status="INACTIVE") == [expense]


def test_journal_pagination_is_tenant_scoped_and_deterministic(db_session: Session) -> None:
    first = create_user(db_session, "pages-first@example.com")
    second = create_user(db_session, "pages-second@example.com")
    account = SqlAccountRepository(db_session, first.id).create(name="Cash", account_type="CASH")
    category = SqlCategoryRepository(db_session, first.id).create(name="Salary", category_type="INCOME")
    foreign_account = SqlAccountRepository(db_session, second.id).create(name="Cash", account_type="CASH")
    repo = SqlJournalRepository(db_session, first.id)
    for amount in ("1.00", "2.00", "3.00"):
        repo.insert_journal(
            kind="INCOME",
            accounting_date=date.today(),
            idempotency_key=uuid.uuid4(),
            lines=(
                JournalLineInput(account_id=account.id, direction="DEBIT", amount=Decimal(amount)),
                JournalLineInput(category_id=category.id, direction="CREDIT", amount=Decimal(amount)),
            ),
        )
    items, total = repo.list_paginated(page=1, page_size=2)
    assert total == 3
    assert len(items) == 2
    assert repo.list_paginated(account_id=foreign_account.id) == ([], 0)


def test_void_journal_is_atomic_and_tenant_scoped(db_session: Session) -> None:
    owner = create_user(db_session, "void-owner@example.com")
    outsider = create_user(db_session, "void-outsider@example.com")
    account = SqlAccountRepository(db_session, owner.id).create(name="Cash", account_type="CASH")
    category = SqlCategoryRepository(db_session, owner.id).create(name="Salary", category_type="INCOME")
    owner_repo = SqlJournalRepository(db_session, owner.id)
    original = owner_repo.insert_journal(
        kind="INCOME",
        accounting_date=date.today(),
        idempotency_key=uuid.uuid4(),
        lines=(
            JournalLineInput(account_id=account.id, direction="DEBIT", amount=Decimal("10.00")),
            JournalLineInput(category_id=category.id, direction="CREDIT", amount=Decimal("10.00")),
        ),
    )
    void_entry = owner_repo.void_journal(
        original.id,
        idempotency_key=uuid.uuid4(),
        account_id=account.id,
        account_version=account.version,
        accounting_date=date.today(),
    )
    assert void_entry.kind == "VOID"
    assert owner_repo.get_by_id(original.id).status == "VOIDED"
    assert SqlAccountRepository(db_session, owner.id).get_by_id(account.id).version == 2

    outsider_repo = SqlJournalRepository(db_session, outsider.id)
    with pytest.raises(ValueError, match="cannot be voided"):
        outsider_repo.void_journal(
            original.id,
            idempotency_key=uuid.uuid4(),
            account_id=account.id,
            account_version=2,
            accounting_date=date.today(),
        )


def test_idempotency_claim_is_atomic_across_connections(
    committed_session_factory: sessionmaker[Session],
) -> None:
    with committed_session_factory.begin() as session:
        owner_id = create_user(session, "concurrent@example.com").id
    key = uuid.uuid4()
    barrier = threading.Barrier(2)
    outcomes: list[bool] = []

    def claimant() -> None:
        with committed_session_factory.begin() as session:
            repository = SqlJournalResponseRepository(session, owner_id)
            barrier.wait()
            outcomes.append(repository.claim(key))

    threads = [threading.Thread(target=claimant) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(outcomes) == [False, True]

    with committed_session_factory.begin() as session:
        repository = SqlJournalResponseRepository(session, owner_id)
        assert repository.complete(key, status_code=201, body={"ok": True}) is True
    with committed_session_factory() as session:
        stored = SqlJournalResponseRepository(session, owner_id).load(key)
        assert stored is not None
        assert stored.status_code == 201
        assert stored.body == {"ok": True}
