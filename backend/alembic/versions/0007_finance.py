"""Money tracking: accounts (debit / credit), spending categories and transactions.

Non-destructive: adds tables and a currency setting. Inserts a starter set of
spending categories (configuration, not personal data); users can rename or archive them.

Revision ID: 0007_finance
Revises: 0006_timeline_hours
Create Date: 2026-10-16
"""

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0007_finance"
down_revision = "0006_timeline_hours"
branch_labels = None
depends_on = None

STARTER_CATEGORIES = [
    ("expense", "Groceries"), ("expense", "Dining out"), ("expense", "Transport"), ("expense", "Housing & rent"),
    ("expense", "Bills & utilities"), ("expense", "Health"), ("expense", "Shopping"), ("expense", "Entertainment"),
    ("expense", "Education"), ("expense", "Other"),
    ("income", "Salary"), ("income", "Other income"),
]


def _ts() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.add_column("app_settings", sa.Column("currency", sa.String(3), nullable=False, server_default="USD"))
    op.alter_column("app_settings", "currency", server_default=None)

    op.create_table(
        "finance_accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("type", sa.String(8), nullable=False),
        sa.Column("opening_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("opened_on", sa.Date(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.CheckConstraint("type IN ('debit', 'credit')", name="ck_finance_accounts_type"),
        sa.PrimaryKeyConstraint("id"),
    )
    categories = op.create_table(
        "finance_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.CheckConstraint("kind IN ('expense', 'income')", name="ck_finance_categories_kind"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "finance_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("finance_accounts.id"), nullable=False),
        sa.Column("to_account_id", sa.Uuid(), sa.ForeignKey("finance_accounts.id"), nullable=True),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("finance_categories.id"), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        *_ts(),
        sa.CheckConstraint("kind IN ('expense', 'income', 'payment')", name="ck_finance_transactions_kind"),
        sa.CheckConstraint("amount_cents > 0", name="ck_finance_transactions_amount"),
        sa.CheckConstraint(
            "(kind = 'payment' AND to_account_id IS NOT NULL AND category_id IS NULL) OR "
            "(kind <> 'payment' AND to_account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_finance_transactions_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_finance_transactions_occurred_on", "finance_transactions", ["occurred_on"])

    now = datetime.now(timezone.utc)
    op.bulk_insert(categories, [
        {"id": uuid.uuid4(), "name": name, "kind": kind, "sort_order": i, "archived_at": None,
         "created_at": now, "updated_at": now}
        for i, (kind, name) in enumerate(STARTER_CATEGORIES)
    ])


def downgrade() -> None:
    # Destructive: removes all money records. Never run automatically.
    op.drop_index("ix_finance_transactions_occurred_on", "finance_transactions")
    op.drop_table("finance_transactions")
    op.drop_table("finance_categories")
    op.drop_table("finance_accounts")
    op.drop_column("app_settings", "currency")
