import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Journal, JournalLine
from app.db.session import transactional_session
from app.domain.ports import JournalLineInput
from app.repositories.accounts_repo import SqlAccountRepository
from app.repositories.categories_repo import SqlCategoryRepository
from app.repositories.journal_responses_repo import SqlJournalResponseRepository
from app.repositories.journals_repo import SqlJournalRepository
from app.repositories.users_repo import SqlUserRepository


def create_user(session: Session, email: str):
    return SqlUserRepository(session).create(email=email, password_hash="hash")


def test_transactional_session_commits_and_rolls_back(
    committed_session_factory: sessionmaker[Session],
) -> None:
    with transactional_session(committed_session_factory) as session:
        create_user(session, "committed@example.com")
    with committed_session_factory() as session:
        assert SqlUserRepository(session).get_by_email("committed@example.com") is not None

    with pytest.raises(RuntimeError):
        with transactional_session(committed_session_factory) as session:
            create_user(session, "rolledback@example.com")
            raise RuntimeError("force rollback")
    with committed_session_factory() as session:
        assert SqlUserRepository(session).get_by_email("rolledback@example.com") is None


def test_account_repository_is_tenant_scoped(db_session: Session) -> None:
    first = create_user(db_session, "account-one@example.com")
    second = create_user(db_session, "account-two@example.com")
    first_repo = SqlAccountRepository(db_session, first.id)
    second_repo = SqlAccountRepository(db_session, second.id)
    account = first_repo.create(name="Cash", account_type="CASH")

    assert first_repo.get_by_id(account.id) is account
    assert second_repo.get_by_id(account.id) is None
    assert second_repo.bump_version(account.id, account.version) == 0
    assert second_repo.get_balance(account.id) is None
    assert first_repo.bump_version(account.id, account.version) == 1


def test_category_repository_is_tenant_scoped_and_clones_seed(db_session: Session) -> None:
    first = create_user(db_session, "category-one@example.com")
    second = create_user(db_session, "category-two@example.com")
    first_repo = SqlCategoryRepository(db_session, first.id)
    second_repo = SqlCategoryRepository(db_session, second.id)
    category = first_repo.create(name="Salary", category_type="INCOME")

    assert second_repo.get_by_id(category.id) is None
    assert second_repo.update(category.id, name="Stolen") is None
    count = first_repo.clone_seed_catalog()
    assert count >= 12
    assert all(item.user_id == first.id for item in first_repo.list())


def test_journal_repository_validates_balance_and_ownership(db_session: Session) -> None:
    first = create_user(db_session, "journal-one@example.com")
    second = create_user(db_session, "journal-two@example.com")
    account = SqlAccountRepository(db_session, first.id).create(name="Cash", account_type="CASH")
    category = SqlCategoryRepository(db_session, first.id).create(name="Salary", category_type="INCOME")
    foreign_category = SqlCategoryRepository(db_session, second.id).create(name="Salary", category_type="INCOME")
    repo = SqlJournalRepository(db_session, first.id)

    with pytest.raises(ValueError, match="balanced"):
        repo.insert_journal(
            kind="INCOME",
            accounting_date=date.today(),
            idempotency_key=uuid.uuid4(),
            lines=(
                JournalLineInput(account_id=account.id, direction="DEBIT", amount=Decimal("10.00")),
                JournalLineInput(category_id=category.id, direction="CREDIT", amount=Decimal("9.00")),
            ),
        )

    with pytest.raises(ValueError, match="tenant"):
        repo.insert_journal(
            kind="INCOME",
            accounting_date=date.today(),
            idempotency_key=uuid.uuid4(),
            lines=(
                JournalLineInput(account_id=account.id, direction="DEBIT", amount=Decimal("10.00")),
                JournalLineInput(category_id=foreign_category.id, direction="CREDIT", amount=Decimal("10.00")),
            ),
        )


def test_journal_insert_balance_and_account_line(db_session: Session) -> None:
    user = create_user(db_session, "journal-valid@example.com")
    account = SqlAccountRepository(db_session, user.id).create(name="Cash", account_type="CASH")
    category = SqlCategoryRepository(db_session, user.id).create(name="Salary", category_type="INCOME")
    repo = SqlJournalRepository(db_session, user.id)
    journal = repo.insert_journal(
        kind="INCOME",
        accounting_date=date.today(),
        idempotency_key=uuid.uuid4(),
        lines=(
            JournalLineInput(account_id=account.id, direction="DEBIT", amount=Decimal("10.00")),
            JournalLineInput(category_id=category.id, direction="CREDIT", amount=Decimal("10.00")),
        ),
    )

    assert db_session.scalar(select(Journal).where(Journal.id == journal.id)) is not None
    assert len(db_session.scalars(select(JournalLine).where(JournalLine.journal_id == journal.id)).all()) == 2
    assert repo.balance_query(account.id) == Decimal("10.00")
    assert repo.get_account_line(journal.id).account_id == account.id


def test_idempotency_claim_is_tenant_scoped(db_session: Session) -> None:
    first = create_user(db_session, "response-one@example.com")
    second = create_user(db_session, "response-two@example.com")
    key = uuid.uuid4()
    first_repo = SqlJournalResponseRepository(db_session, first.id)
    second_repo = SqlJournalResponseRepository(db_session, second.id)

    assert first_repo.claim(key) is True
    assert first_repo.claim(key) is False
    assert second_repo.claim(key) is True
    first_repo.complete(key, status_code=201, body={"amount": "10.00"})
    assert first_repo.load(key).status_code == 201
    assert second_repo.load(key) is None
