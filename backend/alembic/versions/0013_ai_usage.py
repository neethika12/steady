"""AI requests per person, for an optional daily limit (AI_DAILY_LIMIT_PER_USER).

Non-destructive: adds one table. Each row is one AI request (feature name and time only; no
prompts or answers). Rows belong to their user and are protected by row-level security.

Revision ID: 0013_ai_usage
Revises: 0012_auth_attempts
Create Date: 2026-10-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_ai_usage"
down_revision = "0012_auth_attempts"
branch_labels = None
depends_on = None

CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"


def upgrade() -> None:
    op.create_table(
        "ai_usage",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
                  server_default=sa.text(CURRENT_USER)),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ai_usage_user_id", "ai_usage", ["user_id"])
    op.execute("GRANT SELECT, INSERT, DELETE ON ai_usage TO steady_app")
    op.execute("ALTER TABLE ai_usage ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE ai_usage FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY owner_only ON ai_usage USING (user_id = {CURRENT_USER}) WITH CHECK (user_id = {CURRENT_USER})")


def downgrade() -> None:
    op.drop_index("ix_ai_usage_user_id", "ai_usage")
    op.drop_table("ai_usage")
