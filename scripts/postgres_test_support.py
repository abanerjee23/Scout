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
def isolated_database(test_url: str):
    schema = "unloop_test_" + uuid4().hex
    admin = postgres_engine(test_url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(test_url)
    scoped = url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
        hide_password=False
    )
    engine = postgres_engine(scoped)
    try:
        migrate(engine)
        yield scoped, engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
