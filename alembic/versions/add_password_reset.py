"""add password_reset_token and password_reset_expires to users

Revision ID: add_password_reset
Revises: add_ad_spend_daily
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_password_reset"
down_revision = "add_ad_spend_daily"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token VARCHAR")
        op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_expires TIMESTAMP WITH TIME ZONE")
    else:
        op.add_column("users", sa.Column("password_reset_token", sa.String(), nullable=True))
        op.add_column("users", sa.Column("password_reset_expires", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_reset_expires")
    op.drop_column("users", "password_reset_token")
