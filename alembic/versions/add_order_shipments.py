"""Add order_shipments table

Revision ID: add_order_shipments
Revises: 
Create Date: 2026-02-13 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_order_shipments'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create order_shipments table."""
    
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    
    # Create order_shipments table only if it doesn't exist
    if "order_shipments" not in tables:
        op.create_table('order_shipments',
            sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
            sa.Column('order_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('orders.id'), nullable=False),
            sa.Column('shopify_fulfillment_id', sa.String(length=255), nullable=True),
            sa.Column('tracking_number', sa.String(length=255), nullable=True),
            sa.Column('courier', sa.String(length=255), nullable=True),
            sa.Column('fulfillment_status', sa.String(length=50), nullable=True),
            sa.Column('delivery_status', sa.String(length=50), nullable=True),
            sa.Column('selloship_status', sa.String(length=50), nullable=True),
            sa.Column('last_synced', sa.DateTime(timezone=True), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        )
        
        # Add comments
        op.execute("COMMENT ON TABLE order_shipments IS 'Stores Shopify fulfillment tracking information for orders'")
        op.execute("COMMENT ON COLUMN order_shipments.order_id IS 'Reference to order this shipment belongs to'")
        op.execute("COMMENT ON COLUMN order_shipments.shopify_fulfillment_id IS 'Shopify fulfillment ID for tracking'")
        op.execute("COMMENT ON COLUMN order_shipments.tracking_number IS 'Tracking number from courier'")
        op.execute("COMMENT ON COLUMN order_shipments.courier IS 'Courier company name'")
        op.execute("COMMENT ON COLUMN order_shipments.fulfillment_status IS 'Fulfillment status from Shopify'")
        op.execute("COMMENT ON COLUMN order_shipments.delivery_status IS 'Current delivery status'")
        op.execute("COMMENT ON COLUMN order_shipments.selloship_status IS 'Status from Selloship tracking'")
        op.execute("COMMENT ON COLUMN order_shipments.last_synced IS 'Last time this shipment was synced with Shopify'")


def downgrade() -> None:
    """Remove order_shipments table."""
    op.drop_table('order_shipments')
