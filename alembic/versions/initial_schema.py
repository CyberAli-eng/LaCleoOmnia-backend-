"""Initial schema: create all base tables from SQLAlchemy models.

Revision ID: initial_schema
Revises:
Create Date: 2026-02-05

Run first on a fresh DB so later migrations (e.g. add_order_address) do not fail
with "relation 'orders' does not exist".
"""
from alembic import op


revision = "initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create all tables from current models. Uses the same metadata as the app.
    from app.database import Base
    from app import models  # noqa: F401 - register models with Base

    connection = op.get_bind()
    Base.metadata.create_all(bind=connection)


def downgrade() -> None:
    # Dropping in reverse dependency order would be verbose; leave empty.
    # Use a fresh DB or manual DROP if you need to reset.
    pass
