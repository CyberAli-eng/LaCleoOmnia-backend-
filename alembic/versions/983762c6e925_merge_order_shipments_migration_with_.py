"""Merge order_shipments migration with main head

Revision ID: 983762c6e925
Revises: 001_create_order_shipments, 8e57edcea0d2
Create Date: 2026-02-12 12:14:12.866507

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '983762c6e925'
down_revision = ('001_create_order_shipments', '8e57edcea0d2')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
