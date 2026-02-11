"""final merge selloship_mappings and expense_rules

Revision ID: 5c43ef134f08
Revises: 8f9c1a2b3d4e, c3a1b0a7c2f1
Create Date: 2026-02-11 16:31:24.998020

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5c43ef134f08'
down_revision = ('8f9c1a2b3d4e', 'c3a1b0a7c2f1')
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
