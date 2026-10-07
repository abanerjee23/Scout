import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from unloop import create_app

from scripts.postgres_test_support import isolated_database, isolated_schema

ORIGIN = "https://testserver"


@pytest.fixture(scope="session")
def postgres():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        if os.environ.get("REQUIRE_POSTGRES_TESTS") == "true":
            pytest.fail("TEST_DATABASE_URL is required; PostgreSQL tests cannot silently skip")
        pytest.skip("Set TEST_DATABASE_URL to run real PostgreSQL integration tests")
    with isolated_database(url) as value:
        yield value


@pytest.fixture
def app_config(postgres):
    url, engine = postgres
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE reports, demo_profiles, demo_sessions CASCADE"))
    return {
        "DATABASE_URL": url,
        "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
        "APP_ORIGIN": ORIGIN,
        "SESSION_COOKIE_SECURE": "true",
    }


@pytest.fixture
def client(app_config):
    with TestClient(create_app(app_config), base_url=ORIGIN) as value:
        yield value
