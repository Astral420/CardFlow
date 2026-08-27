"""add durable background batch deletion state

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-27 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Commit the enum value before later transactions may write it. This
    # matches the repository's existing enum-migration convention.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE batch_status ADD VALUE IF NOT EXISTS 'deleting'")

    op.add_column(
        "batches",
        sa.Column("deletion_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("deletion_previous_status", sa.String(), nullable=True),
    )
    op.add_column(
        "batches",
        sa.Column("deletion_requested_by", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_batches_deletion_requested_by_users",
        "batches",
        "users",
        ["deletion_requested_by"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_batches_deletion_requested_at",
        "batches",
        ["deletion_requested_at"],
        unique=False,
    )


def downgrade() -> None:
    # PostgreSQL cannot safely remove one enum value in place. A partial
    # downgrade would leave Alembic's version inconsistent with the schema.
    raise NotImplementedError(
        "Cannot automatically downgrade background batch deletion: PostgreSQL "
        "does not support removing enum values."
    )
