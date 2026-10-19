"""Repeating money entries (monthly bills, salary, subscriptions...).

Non-destructive: adds a table and a nullable link column on finance_transactions.

Revision ID: 0008_finance_recurring
Revises: 0007_finance
Create Date: 2026-10-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0008_finance_recurring"
down_revision = "0007_finance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_recurring",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("kind", sa.String(8), nullable=False),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("account_id", sa.Uuid(), sa.ForeignKey("finance_accounts.id"), nullable=False),
        sa.Column("to_account_id", sa.Uuid(), sa.ForeignKey("finance_accounts.id"), nullable=True),
        sa.Column("category_id", sa.Uuid(), sa.ForeignKey("finance_categories.id"), nullable=True),
        sa.Column("frequency", sa.String(8), nullable=False),
        sa.Column("interval", sa.Integer(), nullable=False),
        sa.Column("anchor_on", sa.Date(), nullable=False),
        sa.Column("posted_count", sa.Integer(), nullable=False),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('expense', 'income', 'payment')", name="ck_finance_recurring_kind"),
        sa.CheckConstraint("amount_cents > 0", name="ck_finance_recurring_amount"),
        sa.CheckConstraint("frequency IN ('weekly', 'monthly', 'yearly')", name="ck_finance_recurring_frequency"),
        sa.CheckConstraint("interval BETWEEN 1 AND 12", name="ck_finance_recurring_interval"),
        sa.CheckConstraint("posted_count >= 0", name="ck_finance_recurring_posted"),
        sa.CheckConstraint(
            "(kind = 'payment' AND to_account_id IS NOT NULL AND category_id IS NULL) OR "
            "(kind <> 'payment' AND to_account_id IS NULL AND category_id IS NOT NULL)",
            name="ck_finance_recurring_shape",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column("finance_transactions", sa.Column(
        "recurring_id", sa.Uuid(), sa.ForeignKey("finance_recurring.id", ondelete="SET NULL"), nullable=True))
    op.create_unique_constraint("uq_finance_transactions_recurring_day", "finance_transactions",
                                ["recurring_id", "occurred_on"])


def downgrade() -> None:
    # Destructive for repeating rules only (entries they added stay). Never run automatically.
    op.drop_constraint("uq_finance_transactions_recurring_day", "finance_transactions")
    op.drop_column("finance_transactions", "recurring_id")
    op.drop_table("finance_recurring")
