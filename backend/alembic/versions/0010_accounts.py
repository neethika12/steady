"""User accounts, and every record belongs to one user, enforced by the database.

- Adds ``users`` and ``auth_sessions``.
- Adds ``user_id`` to every data table. Existing rows (from before accounts existed) are given
  to a placeholder "owner" account with no email or password; the first account created on a
  server started with CLAIM_EXISTING_DATA=true takes it over (see services/auth.py). Nothing
  is deleted or rewritten apart from that ownership column.
- ``app_settings`` and ``finance_splitwise`` change from a single row (id = 1) to one row per user.
- Journal dates become unique per user instead of globally.
- Turns on PostgreSQL row-level security: the app runs as the role ``steady_app``, which can
  only see and write rows whose user_id matches the signed-in user (``app.user_id``, set per
  transaction). A forgotten filter in application code therefore can't leak another user's data.

Revision ID: 0010_accounts
Revises: 0009_splitwise
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0010_accounts"
down_revision = "0009_splitwise"
branch_labels = None
depends_on = None

OWNER_ID = "00000000-0000-4000-8000-000000000001"
APP_ROLE = "steady_app"
CURRENT_USER = "NULLIF(current_setting('app.user_id', true), '')::uuid"
TABLES = ["inbox_items", "tasks", "task_plans", "habits", "habit_schedules", "habit_pauses", "habit_checkins",
          "journal_entries", "audit_log", "finance_accounts", "finance_categories", "finance_recurring",
          "finance_transactions"]
PER_USER_ROW = ["app_settings", "finance_splitwise"]  # were single-row (id = 1) tables


def _ts() -> list[sa.Column]:
    return [sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(254), nullable=True),  # empty only for the placeholder owner
        sa.Column("password_hash", sa.String(255), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        *_ts(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),  # sha256 of the cookie value; the value itself isn't stored
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        *_ts(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_auth_sessions_token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])

    conn = op.get_bind()
    has_data = any(conn.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {t})")).scalar() for t in TABLES + PER_USER_ROW)
    if has_data:
        conn.execute(sa.text("INSERT INTO users (id, email, password_hash, created_at, updated_at) "
                             "VALUES (:id, NULL, NULL, now(), now())"), {"id": OWNER_ID})

    for t in TABLES + PER_USER_ROW:
        op.add_column(t, sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True))
        if has_data:
            conn.execute(sa.text(f"UPDATE {t} SET user_id = :id"), {"id": OWNER_ID})
        op.alter_column(t, "user_id", nullable=False, server_default=sa.text(CURRENT_USER))
        if t in TABLES:
            op.create_index(f"ix_{t}_user_id", t, ["user_id"])

    for t in PER_USER_ROW:
        op.drop_constraint(f"ck_{t}_single_row", t, type_="check")
        op.drop_constraint(f"{t}_pkey", t, type_="primary")
        op.drop_column(t, "id")
        op.create_primary_key(f"{t}_pkey", t, ["user_id"])

    op.drop_constraint("uq_journal_entries_entry_date", "journal_entries", type_="unique")
    op.create_unique_constraint("uq_journal_entries_user_date", "journal_entries", ["user_id", "entry_date"])

    # The runtime role. NOLOGIN: the app connects with the normal credentials and switches to it.
    op.execute(f"DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{APP_ROLE}') "
               f"THEN CREATE ROLE {APP_ROLE} NOLOGIN; END IF; END $$")
    op.execute(f"GRANT {APP_ROLE} TO CURRENT_USER")
    op.execute(f"GRANT USAGE ON SCHEMA public TO {APP_ROLE}")
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {APP_ROLE}")
    op.execute(f"REVOKE ALL ON alembic_version FROM {APP_ROLE}")
    op.execute(f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {APP_ROLE}")

    for t in TABLES + PER_USER_ROW:
        op.execute(f"ALTER TABLE {t} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY owner_only ON {t} USING (user_id = {CURRENT_USER}) WITH CHECK (user_id = {CURRENT_USER})")


def downgrade() -> None:
    # Only possible while a single account exists (its data goes back to being "the" data).
    # Never run automatically.
    conn = op.get_bind()
    if conn.execute(sa.text("SELECT count(*) FROM users")).scalar() > 1:
        raise RuntimeError("More than one account exists; downgrading would mix their data. Refusing.")
    for t in TABLES + PER_USER_ROW:
        op.execute(f"DROP POLICY IF EXISTS owner_only ON {t}")
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {t} DISABLE ROW LEVEL SECURITY")
    op.drop_constraint("uq_journal_entries_user_date", "journal_entries", type_="unique")
    op.create_unique_constraint("uq_journal_entries_entry_date", "journal_entries", ["entry_date"])
    for t in PER_USER_ROW:
        op.drop_constraint(f"{t}_pkey", t, type_="primary")
        op.add_column(t, sa.Column("id", sa.Integer(), nullable=False, server_default="1"))
        op.alter_column(t, "id", server_default=None)
        op.create_primary_key(f"{t}_pkey", t, ["id"])
        op.create_check_constraint(f"ck_{t}_single_row", t, "id = 1")
    for t in TABLES + PER_USER_ROW:
        if t in TABLES:
            op.drop_index(f"ix_{t}_user_id", t)
        op.drop_column(t, "user_id")
    op.drop_index("ix_auth_sessions_user_id", "auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("users")
