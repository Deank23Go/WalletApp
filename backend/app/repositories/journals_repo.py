from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any, cast

from sqlalchemy import case, func, select, text, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, joinedload

from app.db.models import Account, Category, Journal, JournalLine
from app.domain.ports import JournalLineInput, JournalRepository
from app.repositories.base import UserScopedRepository


class SqlJournalRepository(UserScopedRepository, JournalRepository):
    def __init__(self, session: Session, user_id: uuid.UUID) -> None:
        super().__init__(session, user_id)

    def _validate_lines(self, kind: str, lines: tuple[JournalLineInput, JournalLineInput]) -> None:
        debit = sum((line.amount for line in lines if line.direction == "DEBIT"), Decimal("0.00"))
        credit = sum((line.amount for line in lines if line.direction == "CREDIT"), Decimal("0.00"))
        if debit != credit:
            raise ValueError("Journal lines must be balanced")
        expected = {"account", "external"} if kind == "OPENING" else {"account", "category"}
        actual: set[str] = set()
        for line in lines:
            references = sum((line.account_id is not None, line.category_id is not None, line.is_external))
            if references != 1 or line.amount <= 0:
                raise ValueError("Each line must have one valid reference and positive amount")
            if line.account_id is not None:
                actual.add("account")
                if self._session.scalar(select(Account.id).where(Account.id == line.account_id, self._tenant_filter(Account.user_id))) is None:
                    raise ValueError("Account does not belong to tenant")
            elif line.category_id is not None:
                actual.add("category")
                if self._session.scalar(select(Category.id).where(Category.id == line.category_id, self._tenant_filter(Category.user_id))) is None:
                    raise ValueError("Category does not belong to tenant")
            else:
                actual.add("external")
        if kind != "VOID" and actual != expected:
            raise ValueError(f"Invalid line references for {kind}")

    def insert_journal(
        self,
        *,
        kind: str,
        accounting_date: date,
        idempotency_key: uuid.UUID,
        lines: tuple[JournalLineInput, JournalLineInput],
        note: str | None = None,
        voided_journal_id: uuid.UUID | None = None,
    ) -> Journal:
        self._validate_lines(kind, lines)
        journal = Journal(
            user_id=self._user_id,
            kind=kind,
            date=accounting_date,
            idempotency_key=idempotency_key,
            note=note,
            voided_journal_id=voided_journal_id,
        )
        self._session.add(journal)
        self._session.flush()
        self._session.add_all(
            [
                JournalLine(
                    journal_id=journal.id,
                    account_id=line.account_id,
                    category_id=line.category_id,
                    is_external=line.is_external,
                    direction=line.direction,
                    amount=line.amount,
                )
                for line in lines
            ]
        )
        self._session.flush()
        return journal

    def get_by_id(self, journal_id: uuid.UUID) -> Journal | None:
        return self._session.scalar(
            select(Journal).options(joinedload(Journal.lines)).where(Journal.id == journal_id, self._tenant_filter(Journal.user_id))
        )

    def list_paginated(
        self,
        *,
        account_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[Journal], int]:
        if page < 1 or page_size < 1:
            raise ValueError("page and page_size must be positive")
        page_size = min(page_size, 100)
        statement = select(Journal).where(self._tenant_filter(Journal.user_id))
        if account_id is not None:
            if self._session.scalar(select(Account.id).where(Account.id == account_id, self._tenant_filter(Account.user_id))) is None:
                return [], 0
            statement = statement.where(Journal.lines.any(JournalLine.account_id == account_id))
        if category_id is not None:
            if self._session.scalar(select(Category.id).where(Category.id == category_id, self._tenant_filter(Category.user_id))) is None:
                return [], 0
            statement = statement.where(Journal.lines.any(JournalLine.category_id == category_id))
        if date_from is not None:
            statement = statement.where(Journal.date >= date_from)
        if date_to is not None:
            statement = statement.where(Journal.date <= date_to)
        total = self._session.scalar(select(func.count()).select_from(statement.subquery())) or 0
        items = list(
            self._session.scalars(
                statement.options(
                    joinedload(Journal.lines).joinedload(JournalLine.account),
                    joinedload(Journal.lines).joinedload(JournalLine.category),
                )
                .order_by(Journal.date.desc(), Journal.created_at.desc(), Journal.id.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).unique()
        )
        return items, total

    def balance_query(self, account_id: uuid.UUID) -> Decimal | None:
        if self._session.scalar(select(Account.id).where(Account.id == account_id, self._tenant_filter(Account.user_id))) is None:
            return None
        value = self._session.scalar(
            select(func.coalesce(func.sum(case((JournalLine.direction == "DEBIT", JournalLine.amount), else_=-JournalLine.amount)), Decimal("0.00"))).where(JournalLine.account_id == account_id)
        )
        return Decimal(str(value))

    def get_account_line(self, journal_id: uuid.UUID) -> JournalLine:
        lines = list(
            self._session.scalars(
                select(JournalLine)
                .join(Journal, Journal.id == JournalLine.journal_id)
                .where(Journal.id == journal_id, self._tenant_filter(Journal.user_id), JournalLine.account_id.is_not(None))
            )
        )
        if len(lines) != 1:
            raise ValueError("Journal must contain exactly one account line")
        return lines[0]

    def void_journal(
        self,
        original_id: uuid.UUID,
        *,
        idempotency_key: uuid.UUID,
        account_id: uuid.UUID,
        account_version: int,
        accounting_date: date,
    ) -> Journal:
        original = self._session.scalar(
            select(Journal)
            .where(Journal.id == original_id, self._tenant_filter(Journal.user_id))
            .with_for_update(of=Journal)
        )
        if original is None or original.status != "POSTED" or original.kind == "VOID":
            raise ValueError("Journal cannot be voided")
        lines = list(
            self._session.scalars(
                select(JournalLine).where(JournalLine.journal_id == original.id)
            )
        )
        account = self._session.scalar(
            select(Account)
            .where(Account.id == account_id, self._tenant_filter(Account.user_id))
            .with_for_update()
        )
        if account is None:
            raise ValueError("Account does not belong to tenant")
        mirror = tuple(
            JournalLineInput(
                account_id=line.account_id,
                category_id=line.category_id,
                is_external=line.is_external,
                direction="CREDIT" if line.direction == "DEBIT" else "DEBIT",
                amount=line.amount,
            )
            for line in lines
        )
        if len(mirror) != 2:
            raise ValueError("Journal must contain exactly two lines")
        void_entry = self.insert_journal(
            kind="VOID",
            accounting_date=accounting_date,
            idempotency_key=idempotency_key,
            lines=(mirror[0], mirror[1]),
            voided_journal_id=original.id,
        )
        journal_update = cast(
            CursorResult[Any],
            self._session.execute(
                update(Journal)
                .where(Journal.id == original.id, self._tenant_filter(Journal.user_id), Journal.status == "POSTED")
                .values(status="VOIDED")
            ),
        )
        account_update = cast(
            CursorResult[Any],
            self._session.execute(
                update(Account)
                .where(
                    Account.id == account_id,
                    self._tenant_filter(Account.user_id),
                    Account.version == account_version,
                )
                .values(version=Account.version + 1, updated_at=text("now()"))
            ),
        )
        if journal_update.rowcount != 1 or account_update.rowcount != 1:
            raise RuntimeError("Concurrency conflict while voiding journal")
        self._session.flush()
        return void_entry
