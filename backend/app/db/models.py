from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    CHAR,
    TIMESTAMP,
    Boolean,
    CheckConstraint,
    Date,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


AccountTypeEnum = Enum("CASH", "BANK", name="account_type")
AccountStatusEnum = Enum("ACTIVE", "INACTIVE", name="account_status")
CategoryTypeEnum = Enum("INCOME", "EXPENSE", name="category_type")
CategoryStatusEnum = Enum("ACTIVE", "INACTIVE", name="category_status")
JournalKindEnum = Enum("OPENING", "INCOME", "EXPENSE", "VOID", name="journal_kind")
JournalStatusEnum = Enum("POSTED", "VOIDED", name="journal_status")
LineDirectionEnum = Enum("DEBIT", "CREDIT", name="line_direction")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint(r"email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'", name="ck_users_email_format"),
        CheckConstraint("preferred_currency ~ '^[A-Z]{3}$'", name="ck_users_currency"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    preferred_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False, server_default=text("'COP'"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    accounts: Mapped[list[Account]] = relationship(back_populates="user", passive_deletes=True)
    categories: Mapped[list[Category]] = relationship(back_populates="user", cascade="all, delete-orphan")
    journals: Mapped[list[Journal]] = relationship(back_populates="user", passive_deletes=True, foreign_keys="Journal.user_id")
    refresh_tokens: Mapped[list[RefreshToken]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
        CheckConstraint("btrim(name) <> ''", name="ck_accounts_name_not_blank"),
        Index("ix_accounts_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    type: Mapped[str] = mapped_column(AccountTypeEnum, nullable=False)
    status: Mapped[str] = mapped_column(AccountStatusEnum, nullable=False, server_default=text("'ACTIVE'"))
    version: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("1"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    user: Mapped[User] = relationship(back_populates="accounts")
    journal_lines: Mapped[list[JournalLine]] = relationship(back_populates="account", passive_deletes=True)


class Category(Base):
    __tablename__ = "categories"
    __table_args__ = (
        UniqueConstraint("user_id", "name", "type", name="uq_categories_user_name_type"),
        CheckConstraint("btrim(name) <> ''", name="ck_categories_name_not_blank"),
        Index("ix_categories_user", "user_id", "type", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    type: Mapped[str] = mapped_column(CategoryTypeEnum, nullable=False)
    is_seed: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    status: Mapped[str] = mapped_column(CategoryStatusEnum, nullable=False, server_default=text("'ACTIVE'"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    user: Mapped[User] = relationship(back_populates="categories")
    journal_lines: Mapped[list[JournalLine]] = relationship(back_populates="category", passive_deletes=True)


class Journal(Base):
    __tablename__ = "journals"
    __table_args__ = (
        UniqueConstraint("user_id", "idempotency_key", name="uq_journals_user_idempotency"),
        CheckConstraint("(kind = 'VOID' AND voided_journal_id IS NOT NULL) OR (kind <> 'VOID' AND voided_journal_id IS NULL)", name="ck_journals_void_link"),
        Index("ix_journals_user_date", "user_id", text("date DESC"), text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    kind: Mapped[str] = mapped_column(JournalKindEnum, nullable=False)
    status: Mapped[str] = mapped_column(JournalStatusEnum, nullable=False, server_default=text("'POSTED'"))
    date: Mapped[date] = mapped_column(Date(), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255))
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    voided_journal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("journals.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    user: Mapped[User] = relationship(back_populates="journals", foreign_keys=[user_id])
    lines: Mapped[list[JournalLine]] = relationship(back_populates="journal", passive_deletes=True)
    voided_journal: Mapped[Journal | None] = relationship(remote_side=[id], foreign_keys=[voided_journal_id])


class JournalLine(Base):
    __tablename__ = "journal_lines"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_lines_amount_positive"),
        CheckConstraint("((account_id IS NOT NULL)::int + (category_id IS NOT NULL)::int + is_external::int) = 1", name="ck_lines_exactly_one_reference"),
        Index("ix_lines_journal", "journal_id"),
        Index("ix_lines_account", "account_id"),
        Index("ix_lines_category", "category_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id", ondelete="RESTRICT"))
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("categories.id", ondelete="RESTRICT"))
    is_external: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default=text("false"))
    direction: Mapped[str] = mapped_column(LineDirectionEnum, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(19, 2), nullable=False)

    journal: Mapped[Journal] = relationship(back_populates="lines")
    account: Mapped[Account | None] = relationship(back_populates="journal_lines")
    category: Mapped[Category | None] = relationship(back_populates="journal_lines")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"
    __table_args__ = (Index("ix_refresh_user", "user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token_hash: Mapped[str] = mapped_column(Text(), nullable=False, unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))

    user: Mapped[User] = relationship(back_populates="refresh_tokens")


class JournalResponse(Base):
    __tablename__ = "journal_responses"
    __table_args__ = (
        CheckConstraint("(state = 'PENDING' AND status_code IS NULL AND body IS NULL) OR (state = 'COMPLETED' AND status_code IS NOT NULL AND body IS NOT NULL)", name="ck_journal_responses_state"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    state: Mapped[str] = mapped_column(String(10), nullable=False, server_default=text("'PENDING'"))
    status_code: Mapped[int | None] = mapped_column(Integer())
    body: Mapped[dict[str, Any] | None] = mapped_column(JSONB())
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
