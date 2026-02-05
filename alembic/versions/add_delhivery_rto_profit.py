"""add Delhivery RTO profit: shipment costs, order_profit new fields, shipment status enum

Revision ID: add_delhivery_rto
Revises: add_webhook_events
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_delhivery_rto"
down_revision = "add_webhook_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        # ALTER TYPE ... ADD VALUE cannot run inside a transaction (PG commits implicitly).
        # Run in a separate autocommit connection so we don't abort the migration transaction.
        engine = conn.engine
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as autocommit_conn:
            # Only extend enum if type "shipmentstatus" exists (old DBs created before initial_schema).
            # After initial_schema, the enum is created with all values; type name may differ (e.g. casing).
            has_type = autocommit_conn.execute(
                sa.text("SELECT 1 FROM pg_catalog.pg_type WHERE typname = 'shipmentstatus'")
            ).scalar() is not None
            if has_type:
                for val in ("RTO_INITIATED", "RTO_DONE", "IN_TRANSIT", "LOST"):
                    try:
                        autocommit_conn.execute(sa.text(f"ALTER TYPE shipmentstatus ADD VALUE '{val}'"))
                    except Exception as e:
                        err = str(e).lower()
                        if "already exists" in err or "duplicate" in err or "does not exist" in err or "undefined" in err:
                            pass  # skip this value
                        else:
                            raise
        # Add columns to shipments
        op.execute("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS forward_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL")
        op.execute("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS reverse_cost NUMERIC(12, 2) DEFAULT 0 NOT NULL")
        op.execute("ALTER TABLE shipments ADD COLUMN IF NOT EXISTS last_synced_at TIMESTAMP")
        # Add columns to order_profit
        op.execute("ALTER TABLE order_profit ADD COLUMN IF NOT EXISTS shipping_forward NUMERIC(12, 2) DEFAULT 0 NOT NULL")
        op.execute("ALTER TABLE order_profit ADD COLUMN IF NOT EXISTS shipping_reverse NUMERIC(12, 2) DEFAULT 0 NOT NULL")
        op.execute("ALTER TABLE order_profit ADD COLUMN IF NOT EXISTS rto_loss NUMERIC(12, 2) DEFAULT 0 NOT NULL")
        op.execute("ALTER TABLE order_profit ADD COLUMN IF NOT EXISTS lost_loss NUMERIC(12, 2) DEFAULT 0 NOT NULL")
        op.execute("ALTER TABLE order_profit ADD COLUMN IF NOT EXISTS courier_status VARCHAR")
        op.execute("ALTER TABLE order_profit ADD COLUMN IF NOT EXISTS final_status VARCHAR")
    else:
        op.add_column("shipments", sa.Column("forward_cost", sa.Numeric(12, 2), server_default="0", nullable=False))
        op.add_column("shipments", sa.Column("reverse_cost", sa.Numeric(12, 2), server_default="0", nullable=False))
        op.add_column("shipments", sa.Column("last_synced_at", sa.DateTime(), nullable=True))
        op.add_column("order_profit", sa.Column("shipping_forward", sa.Numeric(12, 2), server_default="0", nullable=False))
        op.add_column("order_profit", sa.Column("shipping_reverse", sa.Numeric(12, 2), server_default="0", nullable=False))
        op.add_column("order_profit", sa.Column("rto_loss", sa.Numeric(12, 2), server_default="0", nullable=False))
        op.add_column("order_profit", sa.Column("lost_loss", sa.Numeric(12, 2), server_default="0", nullable=False))
        op.add_column("order_profit", sa.Column("courier_status", sa.String(), nullable=True))
        op.add_column("order_profit", sa.Column("final_status", sa.String(), nullable=True))


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE shipments DROP COLUMN IF EXISTS forward_cost")
        op.execute("ALTER TABLE shipments DROP COLUMN IF EXISTS reverse_cost")
        op.execute("ALTER TABLE shipments DROP COLUMN IF EXISTS last_synced_at")
        op.execute("ALTER TABLE order_profit DROP COLUMN IF EXISTS shipping_forward")
        op.execute("ALTER TABLE order_profit DROP COLUMN IF EXISTS shipping_reverse")
        op.execute("ALTER TABLE order_profit DROP COLUMN IF EXISTS rto_loss")
        op.execute("ALTER TABLE order_profit DROP COLUMN IF EXISTS lost_loss")
        op.execute("ALTER TABLE order_profit DROP COLUMN IF EXISTS courier_status")
        op.execute("ALTER TABLE order_profit DROP COLUMN IF EXISTS final_status")
    else:
        op.drop_column("order_profit", "final_status")
        op.drop_column("order_profit", "courier_status")
        op.drop_column("order_profit", "lost_loss")
        op.drop_column("order_profit", "rto_loss")
        op.drop_column("order_profit", "shipping_reverse")
        op.drop_column("order_profit", "shipping_forward")
        op.drop_column("shipments", "last_synced_at")
        op.drop_column("shipments", "reverse_cost")
        op.drop_column("shipments", "forward_cost")
