"""Explicit same-origin web/migration entry points; never print configuration."""

import argparse
import os
from pathlib import Path

import uvicorn
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from unloop.database import Settings, postgres_engine


def migrate():
    settings = Settings.load()
    if not settings.production or settings.database_schema != "unloop_app":
        raise RuntimeError("Production schema configuration required")
    admin = postgres_engine(settings.database_url, production=True)
    try:
        with admin.begin() as db:
            # Exact server-owned identifier, never arbitrary SQL or global settings.
            db.execute(text('CREATE SCHEMA IF NOT EXISTS "unloop_app"'))
    finally:
        admin.dispose()
    engine = postgres_engine(settings.database_url, schema="unloop_app", production=True)
    try:
        with engine.connect() as db:
            config = Config(str(Path("alembic.ini")))
            config.attributes["connection"] = db
            command.upgrade(config, "head")
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["web", "migrate"])
    args = parser.parse_args()
    if args.command == "migrate":
        try:
            migrate()
        except Exception:
            parser.exit(
                1, "Production migration failed; verify private configuration/permissions.\n"
            )
    else:
        # OAuth callback codes must never appear in Uvicorn access logs.
        uvicorn.run(
            "unloop:create_app",
            factory=True,
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8000")),
            access_log=False,
            log_level="warning",
        )


if __name__ == "__main__":
    main()
