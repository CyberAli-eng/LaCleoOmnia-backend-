"""add app_secret_encrypted to shopify_integrations for webhook verification

Revision ID: add_shopify_app_secret
Revises: add_provider_creds
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_shopify_app_secret"
down_revision = "add_provider_creds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE shopify_integrations ADD COLUMN IF NOT EXISTS app_secret_encrypted VARCHAR")
    else:
        try:
            op.add_column("shopify_integrations", sa.Column("app_secret_encrypted", sa.String(), nullable=True))
        except Exception:
            pass  # column may exist


def downgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("ALTER TABLE shopify_integrations DROP COLUMN IF EXISTS app_secret_encrypted")
    else:
        op.drop_column("shopify_integrations", "app_secret_encrypted")
