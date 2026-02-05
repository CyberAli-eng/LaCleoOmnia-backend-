"""add ad_spend_daily table (marketing CAC sync)

Revision ID: add_ad_spend_daily
Revises: add_shopify_app_secret
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_ad_spend_daily"
down_revision = "add_shopify_app_secret"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("""
            CREATE TABLE IF NOT EXISTS ad_spend_daily (
                id VARCHAR NOT NULL PRIMARY KEY,
                date DATE NOT NULL,
                platform VARCHAR NOT NULL,
                spend NUMERIC(12, 2) DEFAULT 0 NOT NULL,
                currency VARCHAR(3) DEFAULT 'INR' NOT NULL,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_ad_spend_daily_date_platform UNIQUE (date, platform)
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_ad_spend_daily_date ON ad_spend_daily (date)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_ad_spend_daily_platform ON ad_spend_daily (platform)")
    else:
        op.create_table(
            "ad_spend_daily",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("platform", sa.String(), nullable=False),
            sa.Column("spend", sa.Numeric(12, 2), default=0, nullable=False),
            sa.Column("currency", sa.String(3), default="INR", nullable=False),
            sa.Column("synced_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("date", "platform", name="uq_ad_spend_daily_date_platform"),
        )
        op.create_index("ix_ad_spend_daily_date", "ad_spend_daily", ["date"])
        op.create_index("ix_ad_spend_daily_platform", "ad_spend_daily", ["platform"])


def downgrade() -> None:
    op.drop_table("ad_spend_daily")
