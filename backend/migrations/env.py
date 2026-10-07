"""Explicit PostgreSQL migrations; no credentials in alembic.ini."""

import os

from alembic import context
from unloop.database import postgres_engine
from unloop.models import Base

config = context.config


def apply(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    raise RuntimeError("Use a configured PostgreSQL connection to run migrations")
elif config.attributes.get("connection") is not None:
    apply(config.attributes["connection"])
else:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required for migrations")
    engine = postgres_engine(database_url)
    try:
        with engine.connect() as connection:
            apply(connection)
    finally:
        engine.dispose()
