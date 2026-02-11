"""add_user_id_to_orders

Revision ID: 8e57edcea0d2
Revises: 5c43ef134f08
Create Date: 2026-02-11 17:02:50.720211

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8e57edcea0d2'
down_revision = '5c43ef134f08'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add user_id column to orders table
    op.add_column('orders', sa.Column('user_id', sa.String(), nullable=True))


def downgrade() -> None:
    # Remove user_id column from orders table
    op.drop_column('orders', 'user_id')
