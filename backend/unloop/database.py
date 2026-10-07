"""PostgreSQL-only connection configuration. Schema changes belong to Alembic."""

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    app_origin: str
    cookie_secure: bool
    session_ttl_seconds: int
    cookie_name: str = "unloop_demo"
    database_schema: str | None = None

    @classmethod
    def load(cls, overrides: dict | None = None):
        values = {**os.environ, **(overrides or {})}
        origin = values.get("APP_ORIGIN", "http://127.0.0.1:5173").rstrip("/")
        parts = urlsplit(origin)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.path:
            raise ValueError("APP_ORIGIN must be an exact HTTP(S) origin without a path")
        secure = str(values.get("SESSION_COOKIE_SECURE", "true")).lower()
        if secure not in {"true", "false"}:
            raise ValueError("SESSION_COOKIE_SECURE must be true or false")
        if secure == "false" and parts.hostname not in {"localhost", "127.0.0.1", "::1"}:
            raise ValueError("Insecure cookies are allowed only for local development")
        ttl = int(values.get("SESSION_TTL_SECONDS", 8 * 60 * 60))
        if not 60 <= ttl <= 24 * 60 * 60:
            raise ValueError("SESSION_TTL_SECONDS must be between 60 and 86400")
        return cls(
            values.get("DATABASE_URL") or None,
            origin,
            secure == "true",
            ttl,
            database_schema=validated_schema(values.get("UNLOOP_TEST_SCHEMA") or None),
        )


class SchemaSelectionError(RuntimeError):
    schema_code = "isolated_schema_selection_failed"


def validated_schema(schema):
    if schema is not None and not re.fullmatch(r"unloop_test_[0-9a-f]{32}", schema):
        raise ValueError("Invalid isolated test schema")
    return schema


def postgres_engine(database_url: str, *, schema=None):
    schema = validated_schema(schema)
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("Unloop persistence requires PostgreSQL")
    engine = create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )

    if schema is not None:

        @event.listens_for(engine, "connect")
        def select_isolated_schema(dbapi_connection, _record):
            # Committed session state survives pool reuse; run on every new socket.
            try:
                with dbapi_connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT set_config('search_path', %s, false), "
                        "set_config('statement_timeout', %s, false), "
                        "set_config('lock_timeout', %s, false)",
                        (schema, "10000", "5000"),
                    )
                    cursor.execute("SELECT current_schema()")
                    if cursor.fetchone()[0] != schema:
                        raise SchemaSelectionError("Isolated schema selection failed")
                dbapi_connection.commit()
            except Exception:
                dbapi_connection.rollback()
                raise

    return engine
