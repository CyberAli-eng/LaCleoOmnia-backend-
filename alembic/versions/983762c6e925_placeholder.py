"""Placeholder for missing revision 983762c6e925

This is a placeholder migration to handle a missing revision that 
exists in the production database but not in the source code.

Revision ID: 983762c6e925
Revises: 9fef252debfb
Create Date: 2026-02-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '983762c6e925'
down_revision = '9fef252debfb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Placeholder migration - no changes needed."""
    pass


def downgrade() -> None:
    """Placeholder migration - no changes needed."""
    pass
