"""batch_audit_logs: durable hard-delete audit trail

Creates a Postgres table that permanently records every batch hard-delete
operation: who performed it, when, what was in the batch, and how many
R2 objects were successfully removed vs. failed.

This table is authoritative -- unlike the Redis obs:recent_batch_deletes
list (which is a best-effort, TTL'd ops-dashboard feed), rows here survive
Redis flushes, container restarts, and server reboots.

Revision ID: a3f91c2d7e04
Revises: 64627611f8cd
Create Date: 2026-08-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a3f91c2d7e04'
down_revision: Union[str, None] = '64627611f8cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "batch_audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        # Raw int, NOT a FK -- the batch row is deleted before we can read it
        # back through a constraint.  History must survive the cascade.
        sa.Column("batch_id", sa.Integer(), nullable=False),
        # NULL when the admin account was deleted after performing the action.
        sa.Column(
            "performed_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        # Action type -- only "hard_delete" for now, extensible later.
        sa.Column("action", sa.String(), nullable=False, server_default="hard_delete"),
        # Snapshot of batch metadata captured at delete time.
        sa.Column("source_label", sa.String(), nullable=True),
        sa.Column("batch_status", sa.String(), nullable=True),
        # Deletion accounting.
        sa.Column("scan_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("r2_keys_deleted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("r2_keys_failed", sa.Integer(), nullable=False, server_default="0"),
        # Free-form notes for partial failures or extra context.
        sa.Column("notes", sa.String(), nullable=True),
    )
    # Index for future audit log queries (e.g. "show all deletes for batch X").
    op.create_index(
        "ix_batch_audit_logs_batch_id",
        "batch_audit_logs",
        ["batch_id"],
    )
    op.create_index(
        "ix_batch_audit_logs_performed_at",
        "batch_audit_logs",
        ["performed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_batch_audit_logs_performed_at", table_name="batch_audit_logs")
    op.drop_index("ix_batch_audit_logs_batch_id", table_name="batch_audit_logs")
    op.drop_table("batch_audit_logs")
