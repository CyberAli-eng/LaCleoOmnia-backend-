"""merge selloship_mappings_v2 and expense_rules branches

Revision ID: 5a22ece1a027
Revises: 2b80af5a7aa5, c3a1b0a7c2f1
Create Date: 2026-02-11 16:16:22.989865

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5a22ece1a027'
down_revision = ('2b80af5a7aa5', 'c3a1b0a7c2f1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
