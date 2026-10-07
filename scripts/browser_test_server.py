"""Real API and disposable PostgreSQL schema for browser tests; no report stubs."""

import os

import uvicorn
from postgres_test_support import isolated_database
from unloop import create_app


def main():
    test_url = os.environ.get("TEST_DATABASE_URL")
    if not test_url:
        raise RuntimeError("TEST_DATABASE_URL is required for real workspace browser tests")
    with isolated_database(test_url) as (database_url, _engine):
        app = create_app(
            {
                "DATABASE_URL": database_url,
                "APP_ORIGIN": "http://127.0.0.1:5173",
                "SESSION_COOKIE_SECURE": "false",
            }
        )
        uvicorn.run(app, host="127.0.0.1", port=5001, log_level="warning")


if __name__ == "__main__":
    main()
