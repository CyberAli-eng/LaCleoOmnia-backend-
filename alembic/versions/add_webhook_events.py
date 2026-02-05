"""add webhook_events table

Revision ID: add_webhook_events
Revises: add_ship_track
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_webhook_events"
down_revision = "add_ship_track"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("""
            CREATE TABLE IF NOT EXISTS webhook_events (
                id VARCHAR NOT NULL PRIMARY KEY,
                source VARCHAR NOT NULL,
                shop_domain VARCHAR,
                topic VARCHAR NOT NULL,
                payload_summary VARCHAR,
                processed_at TIMESTAMP,
                error VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_source ON webhook_events (source)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_shop_domain ON webhook_events (shop_domain)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_topic ON webhook_events (topic)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_webhook_events_created_at ON webhook_events (created_at)")
    else:
        op.create_table(
            "webhook_events",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("shop_domain", sa.String(), nullable=True),
            sa.Column("topic", sa.String(), nullable=False),
            sa.Column("payload_summary", sa.String(), nullable=True),
            sa.Column("processed_at", sa.DateTime(), nullable=True),
            sa.Column("error", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_webhook_events_source", "webhook_events", ["source"])
        op.create_index("ix_webhook_events_shop_domain", "webhook_events", ["shop_domain"])
        op.create_index("ix_webhook_events_topic", "webhook_events", ["topic"])
        op.create_index("ix_webhook_events_created_at", "webhook_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("webhook_events")
