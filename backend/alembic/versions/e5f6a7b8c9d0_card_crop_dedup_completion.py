"""track durable duplicate-detection completion on card crops

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-26 00:00:00.000000

Only front crops are hashed and deduplicated. Existing confirmed front crops
with hashes are treated as already processed during the backfill; new and
re-rotated fronts remain NULL until find_duplicates completes successfully.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "card_crops",
        sa.Column("dedup_completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_card_crops_dedup_completed_at",
        "card_crops",
        ["dedup_completed_at"],
    )
    op.execute(
        """
        UPDATE card_crops AS crop
        SET dedup_completed_at = COALESCE(crop.rotation_confirmed_at, now())
        FROM raw_scans AS scan
        WHERE crop.raw_scan_id = scan.id
          AND scan.side = 'front'
          AND scan.status IN ('cropped', 'skipped')
          AND crop.rotation_confirmed_at IS NOT NULL
          AND crop.hash_0 IS NOT NULL
        """
    )


def downgrade() -> None:
    op.drop_index("ix_card_crops_dedup_completed_at", table_name="card_crops")
    op.drop_column("card_crops", "dedup_completed_at")
