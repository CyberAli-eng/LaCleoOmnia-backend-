"""add order shipping_address and billing_address

Revision ID: add_order_address
Revises:
Create Date: 2025-01-24

"""
from alembic import op


revision = "add_order_address"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        # Idempotent: safe to run multiple times (e.g. on every deploy)
        op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS shipping_address VARCHAR")
        op.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS billing_address VARCHAR")
    else:
        import sqlalchemy as sa
        op.add_column("orders", sa.Column("shipping_address", sa.String(), nullable=True))
        op.add_column("orders", sa.Column("billing_address", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "billing_address")
    op.drop_column("orders", "shipping_address")
