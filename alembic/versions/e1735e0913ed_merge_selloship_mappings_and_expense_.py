"""merge selloship_mappings and expense_rules branches

Revision ID: e1735e0913ed
Revises: add_selloship_mappings_table, c3a1b0a7c2f1
Create Date: 2026-02-11 16:08:53.534194

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e1735e0913ed'
down_revision = ('add_selloship_mappings_table', 'c3a1b0a7c2f1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
