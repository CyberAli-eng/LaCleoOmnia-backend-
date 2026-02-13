"""Merge migrations - Consolidate multiple heads

This migration consolidates multiple head revisions that were created
during the cleanup process. It merges all current heads into a single
revision to resolve the "Multiple head revisions" error.

Revision ID: merge_cleanup_20240213
Revises: 8e57edcea0d2, 8f9c1a2b3d4e, c3a1b0a7c2f1
Create Date: 2026-02-13 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'merge_cleanup_20240213'
down_revision = ('8e57edcea0d2', '8f9c1a2b3d4e', 'c3a1b0a7c2f1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Merge migration - no changes needed."""
    pass


def downgrade() -> None:
    """Merge migration - no changes needed."""
    pass
