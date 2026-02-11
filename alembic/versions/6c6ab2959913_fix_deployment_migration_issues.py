"""fix deployment migration issues

Revision ID: 6c6ab2959913
Revises: 5a22ece1a027
Create Date: 2026-02-11 16:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6c6ab2959913'
down_revision = '5a22ece1a027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This migration is a no-op - it just ensures we can get past the deployment issue
    # The actual selloship_mappings table will be created by the 2b80af5a7aa5 migration
    pass


def downgrade() -> None:
    pass
