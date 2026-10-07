"""Disposable test schema in an explicitly supplied PostgreSQL test database."""

from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.engine import make_url
from unloop.database import postgres_engine

ROOT = Path(__file__).resolve().parents[1]


def migrate(engine):
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@contextmanager
def isolated_database(test_url: str, *, require_tls=False):
    schema = "unloop_test_" + uuid4().hex
    admin = postgres_engine(test_url)
    engine = None
    created = False
    try:
        with admin.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            if (
                require_tls
                and connection.scalar(
                    text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
                )
                is not True
            ):
                raise RuntimeError("TLS connection required")
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        url = make_url(test_url)
        scoped = url.update_query_dict(
            {"options": f"-csearch_path={schema} -cstatement_timeout=10000 -clock_timeout=5000"}
        ).render_as_string(hide_password=False)
        engine = postgres_engine(scoped)
        # Verify the actual selected schema before any Alembic operation. A pooler
        # that drops startup options must fail instead of migrating public.
        with engine.connect() as connection:
            if connection.scalar(text("SELECT current_schema()")) != schema:
                raise RuntimeError("Isolated schema selection failed")
            if (
                require_tls
                and connection.scalar(
                    text("SELECT ssl FROM pg_stat_ssl WHERE pid=pg_backend_pid()")
                )
                is not True
            ):
                raise RuntimeError("TLS connection required")
        migrate(engine)
        yield scoped, engine
    finally:
        if engine is not None:
            engine.dispose()
        try:
            if created:
                with admin.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            admin.dispose()
