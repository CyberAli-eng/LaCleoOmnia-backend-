"""add shipment_tracking table (Delhivery prep)

Revision ID: add_ship_track
Revises: add_sku_profit
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_ship_track"
down_revision = "add_sku_profit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("""
            CREATE TABLE IF NOT EXISTS shipment_tracking (
                id VARCHAR NOT NULL PRIMARY KEY,
                shipment_id VARCHAR NOT NULL REFERENCES shipments(id) ON DELETE CASCADE,
                waybill VARCHAR NOT NULL,
                status VARCHAR,
                delivery_status VARCHAR,
                rto_status VARCHAR,
                raw_response JSONB,
                last_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_shipment_tracking_shipment_id ON shipment_tracking (shipment_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_shipment_tracking_waybill ON shipment_tracking (waybill)")
    else:
        op.create_table(
            "shipment_tracking",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("shipment_id", sa.String(), sa.ForeignKey("shipments.id", ondelete="CASCADE"), nullable=False),
            sa.Column("waybill", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=True),
            sa.Column("delivery_status", sa.String(), nullable=True),
            sa.Column("rto_status", sa.String(), nullable=True),
            sa.Column("raw_response", sa.JSON(), nullable=True),
            sa.Column("last_updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_shipment_tracking_shipment_id", "shipment_tracking", ["shipment_id"])
        op.create_index("ix_shipment_tracking_waybill", "shipment_tracking", ["waybill"])


def downgrade() -> None:
    op.drop_table("shipment_tracking")
