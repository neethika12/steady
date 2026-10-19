"""Accounts get a name (asked when creating an account).

Non-destructive: adds one nullable column. Accounts created before this have no name until
they set one; the app then shows their email instead.

Revision ID: 0011_user_name
Revises: 0010_accounts
Create Date: 2026-10-19
"""

import sqlalchemy as sa
from alembic import op

revision = "0011_user_name"
down_revision = "0010_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("name", sa.String(80), nullable=True))


def downgrade() -> None:
    # Destructive: removes the names. Never run automatically.
    op.drop_column("users", "name")
