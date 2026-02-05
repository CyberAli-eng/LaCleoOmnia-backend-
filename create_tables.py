"""
Create base tables from SQLAlchemy models.
Run this before `alembic upgrade head` on a fresh database (e.g. Render) so that
the root migration (which only ALTERs existing tables) does not fail with
"relation 'orders' does not exist".
"""
from app.database import engine, Base
from app import models  # noqa: F401 - register all models with Base

Base.metadata.create_all(bind=engine)
print("Base tables created (or already exist).")
