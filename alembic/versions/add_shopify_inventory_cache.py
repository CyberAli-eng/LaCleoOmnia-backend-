"""add shopify_inventory cache table

Revision ID: add_shopify_inv
Revises: add_order_address
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_shopify_inv"
down_revision = "add_order_address"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("""
            CREATE TABLE IF NOT EXISTS shopify_inventory (
                id VARCHAR NOT NULL PRIMARY KEY,
                shop_domain VARCHAR NOT NULL,
                sku VARCHAR NOT NULL,
                product_name VARCHAR,
                variant_id VARCHAR,
                inventory_item_id VARCHAR,
                location_id VARCHAR,
                available INTEGER DEFAULT 0,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT shopify_inventory_shop_sku_loc_unique UNIQUE (shop_domain, sku, location_id)
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_shopify_inventory_shop_domain ON shopify_inventory (shop_domain)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_shopify_inventory_sku ON shopify_inventory (sku)")
    else:
        op.create_table(
            "shopify_inventory",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("shop_domain", sa.String(), nullable=False),
            sa.Column("sku", sa.String(), nullable=False),
            sa.Column("product_name", sa.String(), nullable=True),
            sa.Column("variant_id", sa.String(), nullable=True),
            sa.Column("inventory_item_id", sa.String(), nullable=True),
            sa.Column("location_id", sa.String(), nullable=True),
            sa.Column("available", sa.Integer(), default=0),
            sa.Column("synced_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("shop_domain", "sku", "location_id", name="shopify_inventory_shop_sku_loc_unique"),
        )
        op.create_index("ix_shopify_inventory_shop_domain", "shopify_inventory", ["shop_domain"])
        op.create_index("ix_shopify_inventory_sku", "shopify_inventory", ["sku"])


def downgrade() -> None:
    op.drop_table("shopify_inventory")
