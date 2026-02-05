"""orders: unique per (channel_id, channel_account_id, channel_order_id)

Allows the same Shopify order to be synced per connected account (e.g. multiple users
connecting the same store). Fixes 500 on sync when constraint was (channel_id, channel_order_id) only.

Revision ID: add_orders_account_unique
Revises: add_password_reset
Create Date: 2025-01-24

"""
from alembic import op


revision = "add_orders_account_unique"
down_revision = "add_password_reset"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_channel_order_unique")
        op.execute(
            "ALTER TABLE orders ADD CONSTRAINT orders_channel_account_order_unique "
            "UNIQUE (channel_id, channel_account_id, channel_order_id)"
        )
    else:
        op.drop_constraint("orders_channel_order_unique", "orders", type_="unique")
        op.create_unique_constraint(
            "orders_channel_account_order_unique",
            "orders",
            ["channel_id", "channel_account_id", "channel_order_id"],
        )


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE orders DROP CONSTRAINT IF EXISTS orders_channel_account_order_unique")
        op.execute("ALTER TABLE orders ADD CONSTRAINT orders_channel_order_unique UNIQUE (channel_id, channel_order_id)")
    else:
        op.drop_constraint("orders_channel_account_order_unique", "orders", type_="unique")
        op.create_unique_constraint("orders_channel_order_unique", "orders", ["channel_id", "channel_order_id"])
