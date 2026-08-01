"""duplicate_candidates: ON DELETE CASCADE for card_crop FKs

The two foreign-key columns on duplicate_candidates that reference
card_crops.id were created without ON DELETE CASCADE, so attempting to
hard-delete a batch (which cascades through raw_scans -> card_crops)
raised a ForeignKeyViolation because duplicate_candidates rows still
held references to the card_crops being removed.

This migration drops both constraints and recreates them with
ON DELETE CASCADE so that deleting a card_crop row automatically
removes any duplicate_candidate rows that reference it -- on either
side of the pair (card_crop_id_a or card_crop_id_b).

Revision ID: b1e82f3a9c05
Revises: a3f91c2d7e04
Create Date: 2026-08-02 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'b1e82f3a9c05'
down_revision: Union[str, None] = 'a3f91c2d7e04'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # card_crop_id_a
    op.drop_constraint(
        'duplicate_candidates_card_crop_id_a_fkey',
        'duplicate_candidates',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'duplicate_candidates_card_crop_id_a_fkey',
        'duplicate_candidates',
        'card_crops',
        ['card_crop_id_a'],
        ['id'],
        ondelete='CASCADE',
    )

    # card_crop_id_b
    op.drop_constraint(
        'duplicate_candidates_card_crop_id_b_fkey',
        'duplicate_candidates',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'duplicate_candidates_card_crop_id_b_fkey',
        'duplicate_candidates',
        'card_crops',
        ['card_crop_id_b'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    # Restore plain FKs without CASCADE (original state)
    op.drop_constraint(
        'duplicate_candidates_card_crop_id_b_fkey',
        'duplicate_candidates',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'duplicate_candidates_card_crop_id_b_fkey',
        'duplicate_candidates',
        'card_crops',
        ['card_crop_id_b'],
        ['id'],
    )

    op.drop_constraint(
        'duplicate_candidates_card_crop_id_a_fkey',
        'duplicate_candidates',
        type_='foreignkey',
    )
    op.create_foreign_key(
        'duplicate_candidates_card_crop_id_a_fkey',
        'duplicate_candidates',
        'card_crops',
        ['card_crop_id_a'],
        ['id'],
    )
