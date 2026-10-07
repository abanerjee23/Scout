"""PostgreSQL-only connection configuration. Schema changes belong to Alembic."""

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    app_origin: str
    cookie_secure: bool
    session_ttl_seconds: int
    cookie_name: str = "unloop_demo"

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
        return cls(values.get("DATABASE_URL") or None, origin, secure == "true", ttl)


def postgres_engine(database_url: str):
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("Unloop persistence requires PostgreSQL")
    return create_engine(
        url.set(drivername="postgresql+psycopg"),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )
