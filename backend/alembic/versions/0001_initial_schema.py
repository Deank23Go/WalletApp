"""Initial transactional schema.

Revision ID: 0001
Revises: None
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels = None
depends_on = None

ENUMS = (
    ("account_type", ("CASH", "BANK")),
    ("account_status", ("ACTIVE", "INACTIVE")),
    ("category_type", ("INCOME", "EXPENSE")),
    ("category_status", ("ACTIVE", "INACTIVE")),
    ("journal_kind", ("OPENING", "INCOME", "EXPENSE", "VOID")),
    ("journal_status", ("POSTED", "VOIDED")),
    ("line_direction", ("DEBIT", "CREDIT")),
)


def upgrade() -> None:
    enum_types = {
        name: postgresql.ENUM(*values, name=name, create_type=False)
        for name, values in ENUMS
    }
    for enum_type in enum_types.values():
        enum_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("preferred_currency", sa.CHAR(3), nullable=False, server_default=sa.text("'COP'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(r"email ~* '^[^@\s]+@[^@\s]+\.[^@\s]+$'", name="ck_users_email_format"),
        sa.CheckConstraint("preferred_currency ~ '^[A-Z]{3}$'", name="ck_users_currency"),
    )
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("type", enum_types["account_type"], nullable=False),
        sa.Column("status", enum_types["account_status"], nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "name", name="uq_accounts_user_name"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_accounts_name_not_blank"),
    )
    op.create_index("ix_accounts_user_id", "accounts", ["user_id"])
    op.create_table(
        "categories",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("type", enum_types["category_type"], nullable=False),
        sa.Column("is_seed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("status", enum_types["category_status"], nullable=False, server_default=sa.text("'ACTIVE'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "name", "type", name="uq_categories_user_name_type"),
        sa.CheckConstraint("btrim(name) <> ''", name="ck_categories_name_not_blank"),
    )
    op.create_index("ix_categories_user", "categories", ["user_id", "type", "status"])
    op.create_table(
        "journals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("kind", enum_types["journal_kind"], nullable=False),
        sa.Column("status", enum_types["journal_status"], nullable=False, server_default=sa.text("'POSTED'")),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("note", sa.String(255)),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("voided_journal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journals.id", ondelete="RESTRICT")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_journals_user_idempotency"),
        sa.CheckConstraint("(kind = 'VOID' AND voided_journal_id IS NOT NULL) OR (kind <> 'VOID' AND voided_journal_id IS NULL)", name="ck_journals_void_link"),
    )
    op.create_index("ix_journals_user_date", "journals", ["user_id", sa.text("date DESC"), sa.text("created_at DESC")])
    op.create_table(
        "journal_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("journal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id", ondelete="RESTRICT")),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("categories.id", ondelete="RESTRICT")),
        sa.Column("is_external", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("direction", enum_types["line_direction"], nullable=False),
        sa.Column("amount", sa.Numeric(19, 2), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_lines_amount_positive"),
        sa.CheckConstraint("((account_id IS NOT NULL)::int + (category_id IS NOT NULL)::int + is_external::int) = 1", name="ck_lines_exactly_one_reference"),
    )
    op.create_index("ix_lines_journal", "journal_lines", ["journal_id"])
    op.create_index("ix_lines_account", "journal_lines", ["account_id"])
    op.create_index("ix_lines_category", "journal_lines", ["category_id"])
    op.create_table(
        "journal_responses",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("state", sa.String(10), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column("status_code", sa.Integer()),
        sa.Column("body", postgresql.JSONB()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("(state = 'PENDING' AND status_code IS NULL AND body IS NULL) OR (state = 'COMPLETED' AND status_code IS NOT NULL AND body IS NOT NULL)", name="ck_journal_responses_state"),
    )
    op.create_table(
        "refresh_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("family_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_refresh_user", "refresh_tokens", ["user_id"])

    op.execute("""
    CREATE FUNCTION enforce_journal_transition() RETURNS trigger AS $$
    BEGIN
      IF NEW.user_id IS DISTINCT FROM OLD.user_id
         OR NEW.kind IS DISTINCT FROM OLD.kind
         OR NEW.date IS DISTINCT FROM OLD.date
         OR NEW.note IS DISTINCT FROM OLD.note
         OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
         OR NEW.voided_journal_id IS DISTINCT FROM OLD.voided_journal_id
         OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
        RAISE EXCEPTION 'journal entries are immutable';
      END IF;
      IF NOT (OLD.kind <> 'VOID' AND OLD.status = 'POSTED' AND NEW.status = 'VOIDED') THEN
        RAISE EXCEPTION 'only POSTED to VOIDED transition is allowed';
      END IF;
      RETURN NEW;
    END $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE FUNCTION reject_ledger_mutation() RETURNS trigger AS $$
    BEGIN
      RAISE EXCEPTION 'ledger entries are immutable';
    END $$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER trg_journals_no_update BEFORE UPDATE ON journals FOR EACH ROW EXECUTE FUNCTION enforce_journal_transition();")
    op.execute("CREATE TRIGGER trg_journals_no_delete BEFORE DELETE ON journals FOR EACH ROW EXECUTE FUNCTION reject_ledger_mutation();")
    op.execute("CREATE TRIGGER trg_lines_no_update BEFORE UPDATE ON journal_lines FOR EACH ROW EXECUTE FUNCTION reject_ledger_mutation();")
    op.execute("CREATE TRIGGER trg_lines_no_delete BEFORE DELETE ON journal_lines FOR EACH ROW EXECUTE FUNCTION reject_ledger_mutation();")


def downgrade() -> None:
    for trigger, table in (("trg_lines_no_delete", "journal_lines"), ("trg_lines_no_update", "journal_lines"), ("trg_journals_no_delete", "journals"), ("trg_journals_no_update", "journals")):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    op.execute("DROP FUNCTION IF EXISTS reject_ledger_mutation()")
    op.execute("DROP FUNCTION IF EXISTS enforce_journal_transition()")
    op.drop_index("ix_refresh_user", table_name="refresh_tokens")
    op.drop_table("refresh_tokens")
    op.drop_table("journal_responses")
    for index in ("ix_lines_category", "ix_lines_account", "ix_lines_journal"):
        op.drop_index(index, table_name="journal_lines")
    op.drop_table("journal_lines")
    op.drop_index("ix_journals_user_date", table_name="journals")
    op.drop_table("journals")
    op.drop_index("ix_categories_user", table_name="categories")
    op.drop_table("categories")
    op.drop_index("ix_accounts_user_id", table_name="accounts")
    op.drop_table("accounts")
    op.drop_table("users")
    for name, _ in reversed(ENUMS):
        op.execute(f"DROP TYPE IF EXISTS {name}")
