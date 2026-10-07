"""Disposable test schema in an explicitly supplied PostgreSQL test database."""

from contextlib import contextmanager, nullcontext
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from unloop.database import SchemaSelectionError, postgres_engine, validated_schema

ROOT = Path(__file__).resolve().parents[1]


class TLSVerificationError(RuntimeError):
    def __init__(self, code):
        self.tls_code = code
        super().__init__("TLS connection required")


def client_tls_in_use(connection):
    """Read libpq's negotiated client hop, including when connected to a pooler."""
    try:
        value = connection.connection.driver_connection.pgconn.ssl_in_use
    except AttributeError:
        raise TLSVerificationError("client_tls_state_missing") from None
    except Exception:
        raise TLSVerificationError("client_tls_state_error") from None
    if type(value) is not bool:
        raise TLSVerificationError("client_tls_state_unknown")
    return value


def require_client_tls(connection):
    if not client_tls_in_use(connection):
        raise TLSVerificationError("client_tls_not_active")


def migrate(engine):
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")


@contextmanager
def isolated_database(test_url: str, *, require_tls=False, phase=None):
    phase = phase or (lambda _stage: nullcontext())
    schema = "unloop_test_" + uuid4().hex
    admin = postgres_engine(test_url)
    engine = None
    created = False
    try:
        with phase("admin_connection"), admin.begin() as connection:
            connection.execute(text("SET LOCAL statement_timeout = '10s'"))
            connection.execute(text("SET LOCAL lock_timeout = '5s'"))
            with phase("admin_tls"):
                if require_tls:
                    require_client_tls(connection)
            with phase("schema_creation"):
                connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        created = True
        scoped = test_url
        engine = postgres_engine(scoped, schema=schema)
        # Verify the actual selected schema before any Alembic operation. A pooler
        # that drops startup options must fail instead of migrating public.
        with phase("scoped_connection"), engine.connect() as connection:
            with phase("scoped_search_path"):
                if connection.scalar(text("SELECT current_schema()")) != schema:
                    raise SchemaSelectionError("Isolated schema selection failed")
            with phase("scoped_tls"):
                if require_tls:
                    require_client_tls(connection)
        with phase("migration"):
            migrate(engine)
        yield scoped, engine
    finally:
        if engine is not None:
            engine.dispose()
        try:
            if created:
                with phase("schema_cleanup"), admin.begin() as connection:
                    connection.execute(text("SET LOCAL statement_timeout = '10s'"))
                    connection.execute(text("SET LOCAL lock_timeout = '5s'"))
                    connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        finally:
            admin.dispose()


def isolated_schema(engine):
    """Derive explicit child/app configuration from the verified isolated engine."""
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    if schema is None:
        raise SchemaSelectionError("Isolated schema selection failed")
    return validated_schema(schema)
