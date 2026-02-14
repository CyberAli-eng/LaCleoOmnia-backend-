"""Final merge migration

This migration consolidates all remaining heads into a single revision.

Revision ID: final_merge_20240214
Revises: c3a1b0a7c2f1, merge_cleanup_20240213
Create Date: 2026-02-14 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'final_merge_20240214'
down_revision = ('c3a1b0a7c2f1', 'merge_cleanup_20240213')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Final merge migration - no changes needed."""
    pass


def downgrade() -> None:
    """Final merge migration - no changes needed."""
    pass
