"""Add selloship_mappings table v2

Revision ID: 2b80af5a7aa5
Revises: 9fef252debfb
Create Date: 2024-02-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '2b80af5a7aa5'
down_revision = '9fef252debfb'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create selloship_mappings table
    op.create_table(
        'selloship_mappings',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('order_id', sa.String(), nullable=False),
        sa.Column('channel_order_id', sa.String(), nullable=False),
        sa.Column('selloship_order_id', sa.String(), nullable=True),
        sa.Column('awb', sa.String(), nullable=True),
        sa.Column('last_checked', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], 'orders.id', ondelete='CASCADE'),
    )
    
    # Create indexes for performance
    op.create_index('ix_selloship_mappings_order_id', 'selloship_mappings', ['order_id'])
    op.create_index('ix_selloship_mappings_channel_order_id', 'selloship_mappings', ['channel_order_id'])
    op.create_index('ix_selloship_mappings_selloship_order_id', 'selloship_mappings', ['selloship_order_id'])
    op.create_index('ix_selloship_mappings_awb', 'selloship_mappings', ['awb'])
    op.create_index('ix_selloship_mappings_last_checked', 'selloship_mappings', ['last_checked'])


def downgrade() -> None:
    op.drop_table('selloship_mappings')
