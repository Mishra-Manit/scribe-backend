"""add_missing_email_unique_constraint

This migration adds the CRITICAL unique constraint on the users.email column
that was missing from the database. The model has unique=True, but the
constraint was never created in the database, causing schema drift.

Without this constraint, duplicate emails could be inserted, breaking
authentication and user lookup logic.

Revision ID: a0cdf47631c6
Revises: 362b63af6741
Create Date: 2026-01-13 15:13:58.630533

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a0cdf47631c6'
down_revision: Union[str, Sequence[str], None] = '362b63af6741'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema - add unique constraint on email."""
    # Create unique constraint on email column
    # This will fail if duplicate emails exist - that would need manual cleanup
    op.create_unique_constraint(
        'users_email_key',  # PostgreSQL naming convention: tablename_columnname_key
        'users',
        ['email']
    )


def downgrade() -> None:
    """Downgrade schema - remove unique constraint on email."""
    op.drop_constraint('users_email_key', 'users', type_='unique')
