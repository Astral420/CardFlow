"""RBAC: add per-user passwords, account creation timestamps

Adds `password_hash` to `users` (nullable -- legacy/seeded users, including
the original Admin, keep authenticating via the shared APP_PASSCODE; only
Reviewer accounts created through the admin user-management UI get their
own hash) and `created_at` (for the account list in that UI), plus a
uniqueness constraint on `users.name` so login-by-name and account
creation can't collide.

Revision ID: 64627611f8cd
Revises: 821dd350b213
Create Date: 2026-07-24 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '64627611f8cd'
down_revision: Union[str, None] = '821dd350b213'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('password_hash', sa.String(), nullable=True))
    op.add_column(
        'users',
        sa.Column(
            'created_at',
            sa.DateTime(timezone=True),
            server_default=sa.text('now()'),
            nullable=False,
        ),
    )
    op.create_unique_constraint('uq_users_name', 'users', ['name'])


def downgrade() -> None:
    op.drop_constraint('uq_users_name', 'users', type_='unique')
    op.drop_column('users', 'created_at')
    op.drop_column('users', 'password_hash')
