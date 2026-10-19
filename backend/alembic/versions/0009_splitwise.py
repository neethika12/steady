"""Splitwise totals: what you should get and what you should pay, entered by hand.

Non-destructive: adds one small table.

Revision ID: 0009_splitwise
Revises: 0008_finance_recurring
Create Date: 2026-10-16
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_splitwise"
down_revision = "0008_finance_recurring"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "finance_splitwise",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("get_cents", sa.BigInteger(), nullable=False),
        sa.Column("pay_cents", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_finance_splitwise_single_row"),
        sa.CheckConstraint("get_cents >= 0 AND pay_cents >= 0", name="ck_finance_splitwise_amounts"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    # Destructive: removes the saved Splitwise totals. Never run automatically.
    op.drop_table("finance_splitwise")
