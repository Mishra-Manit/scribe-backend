"""remove_redundant_email_index

This migration removes the redundant ix_users_email index that was
explicitly defined in __table_args__. The email column still has a
unique constraint (from unique=True), which automatically provides
indexing functionality. Having both was redundant.

Revision ID: 362b63af6741
Revises: 86348643ad0b
Create Date: 2026-01-13 15:12:24.214888

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision: str = '362b63af6741'
down_revision: Union[str, Sequence[str], None] = '86348643ad0b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - remove redundant email index if it exists."""
    # Get database connection to check if index exists
    conn = op.get_bind()
    inspector = inspect(conn)

    # Get all indexes on the users table
    indexes = inspector.get_indexes('users')
    index_names = [idx['name'] for idx in indexes]

    # Drop the old explicit index if it exists
    # The unique constraint index (from unique=True) will remain
    if 'ix_users_email' in index_names:
        op.drop_index('ix_users_email', table_name='users')


def downgrade() -> None:
    """Downgrade schema - recreate the redundant index."""
    # Recreate the explicit index if downgrading
    # (though this is redundant since unique constraint provides indexing)
    op.create_index('ix_users_email', 'users', ['email'])
