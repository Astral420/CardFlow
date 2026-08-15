"""batch_exports table for cached R2 ZIP exports

Revision ID: c2d3e4f5a6b7
Revises: b1e82f3a9c05
Create Date: 2026-08-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1e82f3a9c05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'batch_exports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column(
            'batch_id',
            sa.Integer(),
            sa.ForeignKey('batches.id', ondelete='CASCADE'),
            nullable=False,
        ),
        sa.Column('manifest_hash', sa.String(length=64), nullable=False),
        sa.Column('r2_key', sa.String(length=255), nullable=False),
        sa.Column('file_size_bytes', sa.BigInteger(), nullable=False),
        sa.Column('image_count', sa.Integer(), nullable=False),
        sa.Column('checksum', sa.String(length=64), nullable=True),
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.UniqueConstraint('batch_id', 'manifest_hash', name='uq_batch_exports_batch_manifest'),
    )
    op.create_index('ix_batch_exports_batch_id', 'batch_exports', ['batch_id'])
    op.create_index('ix_batch_exports_manifest_hash', 'batch_exports', ['manifest_hash'])


def downgrade() -> None:
    op.drop_index('ix_batch_exports_manifest_hash', table_name='batch_exports')
    op.drop_index('ix_batch_exports_batch_id', table_name='batch_exports')
    op.drop_table('batch_exports')
