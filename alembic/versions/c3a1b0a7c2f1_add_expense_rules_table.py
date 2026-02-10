"""add expense_rules table (versioned expense configuration)

Revision ID: c3a1b0a7c2f1
Revises: e076b7128e37
Create Date: 2026-02-10
"""

from alembic import op


# revision identifiers, used by Alembic.
revision = "c3a1b0a7c2f1"
down_revision = "e076b7128e37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent: safe to rerun
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS expense_rules (
            id VARCHAR PRIMARY KEY,
            user_id VARCHAR NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            type VARCHAR NOT NULL,
            name VARCHAR NOT NULL,
            value NUMERIC(12, 4) NOT NULL DEFAULT 0,
            value_type VARCHAR NOT NULL,
            effective_from DATE NOT NULL,
            effective_to DATE NULL,
            platform VARCHAR NULL,
            created_at TIMESTAMP DEFAULT now(),
            updated_at TIMESTAMP DEFAULT now()
        );
        """
    )

    op.execute("CREATE INDEX IF NOT EXISTS ix_expense_rules_user_id ON expense_rules (user_id);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_expense_rules_type ON expense_rules (type);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_expense_rules_effective_from ON expense_rules (effective_from);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_expense_rules_effective_to ON expense_rules (effective_to);")
    op.execute("CREATE INDEX IF NOT EXISTS ix_expense_rules_platform ON expense_rules (platform);")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_expense_rules_user_type_from_platform "
        "ON expense_rules (user_id, type, effective_from, COALESCE(platform, ''));"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS expense_rules;")

