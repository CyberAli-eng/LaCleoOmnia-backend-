"""Add selloship_mappings table - final fix

Revision ID: 8f9c1a2b3d4e
Revises: 983762c6e925
Create Date: 2024-02-11 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f9c1a2b3d4e'
down_revision = '983762c6e925'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    tables = set(inspector.get_table_names())
    
    # Create selloship_mappings table if it doesn't exist
    if "selloship_mappings" not in tables:
        # Create selloship_mappings table without foreign key
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
        )
        
        # Create indexes for performance
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("selloship_mappings")}
        if "ix_selloship_mappings_order_id" not in existing_indexes:
            op.create_index('ix_selloship_mappings_order_id', 'selloship_mappings', ['order_id'])
        if "ix_selloship_mappings_channel_order_id" not in existing_indexes:
            op.create_index('ix_selloship_mappings_channel_order_id', 'selloship_mappings', ['channel_order_id'])
        if "ix_selloship_mappings_selloship_order_id" not in existing_indexes:
            op.create_index('ix_selloship_mappings_selloship_order_id', 'selloship_mappings', ['selloship_order_id'])
        if "ix_selloship_mappings_awb" not in existing_indexes:
            op.create_index('ix_selloship_mappings_awb', 'selloship_mappings', ['awb'])
        if "ix_selloship_mappings_last_checked" not in existing_indexes:
            op.create_index('ix_selloship_mappings_last_checked', 'selloship_mappings', ['last_checked'])


def downgrade() -> None:
    op.drop_table('selloship_mappings')
