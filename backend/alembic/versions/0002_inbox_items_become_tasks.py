"""The Inbox now holds tasks only: turn open inbox items into undated tasks.

Non-destructive: nothing is deleted. Each open inbox item gets a new task whose title
is the item's first line (full text kept in the description when longer); the item is
marked converted and linked to the task, and an audit row records the change.
Archived and already-converted items are left exactly as they are.

Revision ID: 0002_inbox_items_become_tasks
Revises: 0001_initial
Create Date: 2026-10-14
"""

from alembic import op

revision = "0002_inbox_items_become_tasks"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(r"""
        WITH src AS (
            SELECT id, btrim(text, E' \t\r\n') AS body, created_at
            FROM inbox_items
            WHERE status = 'open'
        ),
        new_tasks AS (
            INSERT INTO tasks (id, title, description, priority, status, source_inbox_item_id, created_at, updated_at)
            SELECT gen_random_uuid(),
                   left(split_part(body, E'\n', 1), 200),
                   CASE WHEN body = left(split_part(body, E'\n', 1), 200) THEN '' ELSE body END,
                   'medium', 'active', id, created_at, now()
            FROM src
            RETURNING id, source_inbox_item_id
        ),
        marked AS (
            UPDATE inbox_items i
            SET status = 'converted', converted_to_type = 'task', converted_to_id = n.id,
                converted_at = now(), updated_at = now()
            FROM new_tasks n
            WHERE i.id = n.source_inbox_item_id
            RETURNING i.id, n.id AS task_id
        )
        INSERT INTO audit_log (id, entity_type, entity_id, action, before, after, note, created_at)
        SELECT gen_random_uuid(), 'inbox_item', m.id, 'converted_to_task', NULL,
               json_build_object('target_ids', json_build_array(m.task_id::text)),
               'Inbox merged into To-Do (migration 0002)', now()
        FROM marked m
    """)


def downgrade() -> None:
    # Intentionally does nothing: the created tasks may since have been planned, reviewed
    # or edited, so removing them would lose history. The links back to the original
    # inbox items are kept in tasks.source_inbox_item_id.
    pass
