"""add provider_credentials table (per-user integration API keys)

Revision ID: add_provider_creds
Revises: add_delhivery_rto
Create Date: 2025-01-24

"""
from alembic import op
import sqlalchemy as sa


revision = "add_provider_creds"
down_revision = "add_delhivery_rto"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    if conn.dialect.name == "postgresql":
        op.execute("""
            CREATE TABLE IF NOT EXISTS provider_credentials (
                id VARCHAR NOT NULL PRIMARY KEY,
                user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                provider_id VARCHAR NOT NULL,
                value_encrypted VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT uq_provider_credentials_user_provider UNIQUE (user_id, provider_id)
            )
        """)
        op.execute("CREATE INDEX IF NOT EXISTS ix_provider_credentials_user_id ON provider_credentials (user_id)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_provider_credentials_provider_id ON provider_credentials (provider_id)")
    else:
        op.create_table(
            "provider_credentials",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("provider_id", sa.String(), nullable=False),
            sa.Column("value_encrypted", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("user_id", "provider_id", name="uq_provider_credentials_user_provider"),
        )
        op.create_index("ix_provider_credentials_user_id", "provider_credentials", ["user_id"])
        op.create_index("ix_provider_credentials_provider_id", "provider_credentials", ["provider_id"])


def downgrade() -> None:
    op.drop_table("provider_credentials")
