"""Login and sign-up attempts, so rate limits hold across several server instances.

Non-destructive: adds one table (attempt timestamps only; no passwords or personal data).

Revision ID: 0012_auth_attempts
Revises: 0011_user_name
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0012_auth_attempts"
down_revision = "0011_user_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "auth_attempts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(320), nullable=False),  # e.g. "login:email:x@y.com", "login:ip:1.2.3.4"
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_auth_attempts_key_created", "auth_attempts", ["key", "created_at"])
    op.execute("GRANT SELECT, INSERT, DELETE ON auth_attempts TO steady_app")


def downgrade() -> None:
    op.drop_index("ix_auth_attempts_key_created", "auth_attempts")
    op.drop_table("auth_attempts")
