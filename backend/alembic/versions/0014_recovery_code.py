"""Recovery codes for "Forgot password" (no email needed).

Non-destructive: adds one nullable column. Only a scrypt hash of the code is stored. Accounts
created before this have no code until they make one from the account menu.

Revision ID: 0014_recovery_code
Revises: 0013_ai_usage
Create Date: 2026-10-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_recovery_code"
down_revision = "0013_ai_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("recovery_code_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    # Destructive: removes recovery codes. Never run automatically.
    op.drop_column("users", "recovery_code_hash")
