"""add composite index for per-user created_at ordering

The memories list endpoints filter by user_id/state and order by created_at
DESC; existing indexes cover (user_id, state) but not the sort, so Postgres
sorts the filtered set on every page. Composite index removes the sort.

Revision ID: b7e2c9d41f30
Revises: afd00efbd06b
Create Date: 2026-07-19
"""
from typing import Sequence, Union

from alembic import op

revision: str = 'b7e2c9d41f30'
down_revision: Union[str, None] = 'afd00efbd06b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'idx_memory_user_created',
        'memories',
        ['user_id', 'created_at'],
        unique=False,
        postgresql_ops={'created_at': 'DESC'},
    )


def downgrade() -> None:
    op.drop_index('idx_memory_user_created', table_name='memories')
