"""Create order_shipments table for Shopify-centric tracking

Revision ID: 001_create_order_shipments
Revises: 
Create Date: 2026-02-12 11:58:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '001_create_order_shipments'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Create order_shipments table
    op.create_table('order_shipments',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=False),
        sa.Column('shopify_fulfillment_id', sa.String(), nullable=True),
        sa.Column('tracking_number', sa.String(), nullable=True),
        sa.Column('courier', sa.String(), nullable=True),
        sa.Column('fulfillment_status', sa.String(), nullable=True),
        sa.Column('delivery_status', sa.String(), nullable=True),
        sa.Column('selloship_status', sa.String(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_order_shipments_order_id', 'order_shipments', ['order_id'])
    op.create_index('ix_order_shipments_tracking_number', 'order_shipments', ['tracking_number'])
    op.create_index('ix_order_shipments_shopify_fulfillment_id', 'order_shipments', ['shopify_fulfillment_id'])
    op.create_index('ix_order_shipments_last_synced_at', 'order_shipments', ['last_synced_at'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_order_shipments_last_synced_at', table_name='order_shipments')
    op.drop_index('ix_order_shipments_shopify_fulfillment_id', table_name='order_shipments')
    op.drop_index('ix_order_shipments_tracking_number', table_name='order_shipments')
    op.drop_index('ix_order_shipments_order_id', table_name='order_shipments')
    
    # Drop table
    op.drop_table('order_shipments')
