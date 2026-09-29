from __future__ import annotations

import builtins
import uuid
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import case, func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from app.db.models import Account, JournalLine
from app.domain.ports import AccountRepository
from app.repositories.base import UserScopedRepository


class SqlAccountRepository(UserScopedRepository, AccountRepository):
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        super().__init__(session, user_id)

    def create(self, *, name: str, account_type: str) -> Account:
        account = Account(user_id=self._user_id, name=name.strip(), type=account_type)
        self._session.add(account)
        self._session.flush()
        return account

    def list(self) -> list[Account]:
        return list(self._session.scalars(select(Account).where(self._tenant_filter(Account.user_id)).order_by(Account.created_at)))

    def list_with_balances(self, *, status: str | None = None) -> builtins.list[tuple[Account, Decimal]]:
        statement = (
            select(
                Account,
                func.coalesce(
                    func.sum(case((JournalLine.direction == "DEBIT", JournalLine.amount), else_=-JournalLine.amount)),
                    Decimal("0.00"),
                ).label("balance"),
            )
            .outerjoin(JournalLine, JournalLine.account_id == Account.id)
            .where(self._tenant_filter(Account.user_id))
            .group_by(Account.id)
            .order_by(Account.created_at)
        )
        if status is not None:
            statement = statement.where(Account.status == status)
        return [(account, Decimal(str(balance))) for account, balance in self._session.execute(statement).all()]

    def get_by_id(self, account_id: uuid.UUID) -> Account | None:
        return self._session.scalar(select(Account).where(Account.id == account_id, self._tenant_filter(Account.user_id)))

    def get_for_update(self, account_id: uuid.UUID) -> Account | None:
        return self._session.scalar(select(Account).where(Account.id == account_id, self._tenant_filter(Account.user_id)).with_for_update())

    def update(self, account_id: uuid.UUID, *, name: str | None = None, status: str | None = None) -> Account | None:
        account = self.get_by_id(account_id)
        if account is None:
            return None
        if name is not None:
            account.name = name.strip()
        if status is not None:
            account.status = status
        self._session.flush()
        return account

    def bump_version(self, account_id: uuid.UUID, expected_version: int) -> int:
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(Account)
                .where(Account.id == account_id, self._tenant_filter(Account.user_id), Account.version == expected_version)
                .values(version=Account.version + 1, updated_at=text("now()"))
            ),
        )
        return result.rowcount

    def get_balance(self, account_id: uuid.UUID) -> Decimal | None:
        if self.get_by_id(account_id) is None:
            return None
        value = self._session.scalar(
            select(
                func.coalesce(
                    func.sum(case((JournalLine.direction == "DEBIT", JournalLine.amount), else_=-JournalLine.amount)),
                    Decimal("0.00"),
                )
            ).where(JournalLine.account_id == account_id)
        )
        return Decimal(str(value))
