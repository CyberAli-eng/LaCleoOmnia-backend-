"""add sku_costs and order_profit tables (profit engine)

Revision ID: add_sku_profit
Revises: add_shopify_inv
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_sku_profit"
down_revision = "add_shopify_inv"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("""
            CREATE TABLE IF NOT EXISTS sku_costs (
                id VARCHAR NOT NULL PRIMARY KEY,
                sku VARCHAR NOT NULL UNIQUE,
                product_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                packaging_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                box_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                inbound_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_sku_costs_sku ON sku_costs (sku)")
        op.execute("""
            CREATE TABLE IF NOT EXISTS order_profit (
                id VARCHAR NOT NULL PRIMARY KEY,
                order_id VARCHAR NOT NULL UNIQUE REFERENCES orders(id) ON DELETE CASCADE,
                revenue NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                product_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                packaging_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                shipping_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                marketing_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                payment_fee NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                net_profit NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                status VARCHAR DEFAULT 'computed' NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_order_profit_order_id ON order_profit (order_id)")
    else:
        op.create_table(
            "sku_costs",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("sku", sa.String(), nullable=False),
            sa.Column("product_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("packaging_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("box_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("inbound_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("sku", name="uq_sku_costs_sku"),
        )
        op.create_index("ix_sku_costs_sku", "sku_costs", ["sku"])
        op.create_table(
            "order_profit",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("order_id", sa.String(), sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
            sa.Column("revenue", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("product_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("packaging_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("shipping_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("marketing_cost", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("payment_fee", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("net_profit", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("status", sa.String(), default="computed", nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("order_id", name="uq_order_profit_order_id"),
        )
        op.create_index("ix_order_profit_order_id", "order_profit", ["order_id"])


def downgrade() -> None:
    op.drop_table("order_profit")
    op.drop_table("sku_costs")
