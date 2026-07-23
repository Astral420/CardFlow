"""pairing_key column + missing indexes

Adds RawScan.pairing_key (backfilled from original_filename using the same
front/back-suffix-stripping rule as app.naming.pairing_key), so the
front/back sibling lookup can use a direct indexed query instead of
loading every scan in a batch and linear-scanning for a filename match.

Also adds the secondary indexes the audit flagged as missing: queries on
card_crops.rotation_confirmed_at and duplicate_candidates.status /
card_crop_id_a / card_crop_id_b were all running as sequential scans.

Revision ID: 821dd350b213
Revises: 1df637c7f6bb
Create Date: 2026-07-23 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '821dd350b213'
down_revision: Union[str, None] = '1df637c7f6bb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- raw_scans.pairing_key ------------------------------------------
    op.add_column("raw_scans", sa.Column("pairing_key", sa.String(), nullable=True))

    # Backfill using the same rule as app.naming.pairing_key: strip a
    # trailing "-front"/"-back" (before the extension) and lowercase it.
    # Imported here rather than reimplemented so the backfill can never
    # drift from the column's own before_insert/before_update computation.
    from app.naming import pairing_key as _pairing_key

    raw_scans = sa.table(
        "raw_scans",
        sa.column("id", sa.Integer),
        sa.column("original_filename", sa.String),
        sa.column("pairing_key", sa.String),
    )
    conn = op.get_bind()
    rows = conn.execute(
        sa.select(raw_scans.c.id, raw_scans.c.original_filename)
    ).fetchall()
    for row_id, original_filename in rows:
        conn.execute(
            raw_scans.update()
            .where(raw_scans.c.id == row_id)
            .values(pairing_key=_pairing_key(original_filename))
        )

    op.alter_column("raw_scans", "pairing_key", nullable=False)
    op.create_index(
        "ix_raw_scans_batch_id_pairing_key",
        "raw_scans",
        ["batch_id", "pairing_key"],
    )

    # --- card_crops.rotation_confirmed_at --------------------------------
    op.create_index(
        "ix_card_crops_rotation_confirmed_at",
        "card_crops",
        ["rotation_confirmed_at"],
    )

    # --- duplicate_candidates ---------------------------------------------
    op.create_index(
        "ix_duplicate_candidates_status", "duplicate_candidates", ["status"]
    )
    op.create_index(
        "ix_duplicate_candidates_card_crop_id_a",
        "duplicate_candidates",
        ["card_crop_id_a"],
    )
    op.create_index(
        "ix_duplicate_candidates_card_crop_id_b",
        "duplicate_candidates",
        ["card_crop_id_b"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_duplicate_candidates_card_crop_id_b", table_name="duplicate_candidates"
    )
    op.drop_index(
        "ix_duplicate_candidates_card_crop_id_a", table_name="duplicate_candidates"
    )
    op.drop_index("ix_duplicate_candidates_status", table_name="duplicate_candidates")
    op.drop_index("ix_card_crops_rotation_confirmed_at", table_name="card_crops")
    op.drop_index("ix_raw_scans_batch_id_pairing_key", table_name="raw_scans")
    op.drop_column("raw_scans", "pairing_key")
