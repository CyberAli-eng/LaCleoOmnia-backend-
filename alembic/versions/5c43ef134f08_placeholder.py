"""Placeholder migration for deleted merge file

This is a placeholder migration to maintain consistency with production database.
The original merge file was deleted during cleanup but the migration history
still references it. This placeholder ensures Alembic can continue working.

Revision ID: 5c43ef134f08
Revises: add_order_shipments
Create Date: 2026-02-13 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '5c43ef134f08'
down_revision = 'add_order_shipments'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Placeholder upgrade - no changes needed."""
    pass


def downgrade() -> None:
    """Placeholder downgrade - no changes needed."""
    pass
