"""Real API and disposable PostgreSQL schema for browser tests; no report stubs."""

import os
import subprocess
import sys

import uvicorn
from postgres_test_support import isolated_database, isolated_schema
from unloop import create_app


def main():
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        raise RuntimeError("TEST_DATABASE_URL is required for real workspace browser tests")
    with isolated_database(test_url) as (database_url, engine):
        app = create_app(
            {
                "DATABASE_URL": database_url,
                "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
                "APP_ORIGIN": "http://127.0.0.1:5173",
                "SESSION_COOKIE_SECURE": "false",
            }
        )
        worker = subprocess.Popen(
            [sys.executable, "-m", "unloop.worker"],
            env={
                "PATH": os.environ.get("PATH", ""),
                "DATABASE_URL": database_url,
                "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
            },
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            uvicorn.run(app, host="127.0.0.1", port=5001, log_level="warning")
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=5)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)


if __name__ == "__main__":
    main()
