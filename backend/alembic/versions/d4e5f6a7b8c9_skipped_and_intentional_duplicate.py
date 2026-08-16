"""add scan_status.skipped and duplicate_status.intentional_duplicate

Revision ID: d4e5f6a7b8c9
Revises: c2d3e4f5a6b7
Create Date: 2026-08-16 00:00:00.000000

scan_status.skipped: an already-cropped/properly-cropped raw scan where the
crop step was a no-op (see app.vision.crop.CropResult.already_cropped) --
distinct from `cropped` (we performed the crop transform) so it's visible
in batch counts, but treated the same as `cropped` everywhere downstream
(rotation review, hashing, dedup, export).

duplicate_status.intentional_duplicate: a duplicate-review decision meaning
"yes, these are the same physical card, and that's expected" (e.g.
multiple copies in inventory) -- unlike confirmed_duplicate, neither side
is excluded from the batch export.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'd4e5f6a7b8c9'
down_revision: Union[str, None] = 'c2d3e4f5a6b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres requires ALTER TYPE ... ADD VALUE to run outside the
    # transaction Alembic normally wraps each migration in (it's a
    # non-transactional DDL operation prior to being visible for use, even
    # though modern Postgres allows the ALTER itself inside a transaction).
    # autocommit_block() runs this migration's statements each in their own
    # implicit transaction instead of Alembic's usual single wrapping one.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE scan_status ADD VALUE IF NOT EXISTS 'skipped'")
        op.execute(
            "ALTER TYPE duplicate_status ADD VALUE IF NOT EXISTS 'intentional_duplicate'"
        )


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Safely removing a value
    # means recreating the enum type (create new type, cast every
    # dependent column over, drop the old type) and only works at all if no
    # existing row still uses the value being dropped -- that's a
    # data-dependent, destructive operation this migration can't safely
    # automate. If you need to downgrade past this revision, first migrate
    # any `skipped` raw_scans / `intentional_duplicate` duplicate_candidates
    # rows to a supported status by hand, then perform the type-recreation
    # manually.
    raise NotImplementedError(
        "Cannot automatically downgrade past d4e5f6a7b8c9: Postgres does not "
        "support removing enum values. See migration docstring."
    )
