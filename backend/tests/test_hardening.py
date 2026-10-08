"""Actual PostgreSQL negative checks and migration of retained Phase 1A rows."""

import os

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from unloop import create_app

from scripts.postgres_test_support import ROOT, isolated_database, isolated_schema

ORIGIN = "https://testserver"


def seed_report(client):
    session = client.post("/api/session", json={}, headers={"Origin": ORIGIN}).json()
    headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrfToken"]}
    proposal = client.post(
        "/api/report-proposals",
        json={"message": "London 2026-10-01 for a client workshop"},
        headers=headers,
    ).json()
    response = client.post(
        "/api/reports",
        headers=headers,
        json={
            "proposalToken": proposal["proposalToken"],
            "confirmed": True,
            "header": proposal["header"],
        },
    )
    assert response.status_code == 201
    return response.json()


@pytest.mark.parametrize(
    "persona, grade",
    [("employee", None), ("employee", "G"), ("employee", ""), ("manager", "C")],
)
def test_database_rejects_invalid_seeded_grade(client, postgres, persona, grade):
    seed_report(client)
    with postgres[1].begin() as connection:
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(
                text("UPDATE demo_profiles SET grade=:grade WHERE persona=:persona"),
                {"grade": grade, "persona": persona},
            )
        assert error.value.orig.diag.constraint_name == "profile_seeded_grade"


@pytest.mark.parametrize("target", ["own_manager", "foreign_employee", "foreign_manager"])
def test_report_profile_enforces_employee_and_owner(client, app_config, postgres, target):
    seed_report(client)
    with TestClient(create_app(app_config), base_url=ORIGIN) as other:
        other.post("/api/session", json={}, headers={"Origin": ORIGIN})
    with postgres[1].begin() as connection:
        owner = connection.scalar(text("SELECT session_id FROM reports"))
        persona = "employee" if target == "foreign_employee" else "manager"
        comparison = "=" if target == "own_manager" else "<>"
        profile = connection.scalar(
            text(
                f"SELECT id FROM demo_profiles WHERE session_id {comparison} :owner "
                "AND persona=:persona"
            ),
            {"owner": owner, "persona": persona},
        )
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.execute(
                text("UPDATE reports SET employee_profile_id=:profile"),
                {"profile": profile},
            )
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text("UPDATE reports SET employee_persona='manager'"))
        assert error.value.orig.diag.constraint_name == "report_employee_only"


def migration_config(connection):
    config = Config(str(ROOT / "alembic.ini"))
    config.attributes["connection"] = connection
    return config


def test_hardening_upgrade_backfill_downgrade_reupgrade(postgres):
    # A separate freshly migrated schema avoids changing the shared test schema.
    with isolated_database(os.environ["TEST_DATABASE_URL"]) as (url, engine):
        with TestClient(
            create_app(
                {
                    "DATABASE_URL": url,
                    "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
                    "APP_ORIGIN": ORIGIN,
                    "SESSION_COOKIE_SECURE": "true",
                }
            ),
            base_url=ORIGIN,
        ) as client:
            report = seed_report(client)
            cookie = dict(client.cookies)
        with engine.begin() as connection:
            config = migration_config(connection)
            command.check(config)
            command.downgrade(config, "0001_phase1a")
            connection.execute(text("UPDATE demo_profiles SET grade=NULL WHERE persona='employee'"))
            connection.execute(
                text(
                    "UPDATE reports SET employee_profile_id="
                    "(SELECT id FROM demo_profiles WHERE persona='manager')"
                )
            )
            command.upgrade(config, "head")
            assert (
                connection.scalar(text("SELECT grade FROM demo_profiles WHERE persona='employee'"))
                == "C"
            )
            assert (
                connection.scalar(
                    text(
                        "SELECT p.persona FROM reports r JOIN demo_profiles p "
                        "ON p.id=r.employee_profile_id"
                    )
                )
                == "employee"
            )
            command.check(config)
            command.downgrade(config, "0001_phase1a")
            command.upgrade(config, "head")
            command.check(config)
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text("UPDATE demo_profiles SET grade=NULL WHERE persona='employee'")
                )
            with pytest.raises(IntegrityError), connection.begin_nested():
                connection.execute(
                    text(
                        "UPDATE reports SET employee_profile_id="
                        "(SELECT id FROM demo_profiles WHERE persona='manager')"
                    )
                )
        with TestClient(
            create_app(
                {
                    "DATABASE_URL": url,
                    "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
                    "APP_ORIGIN": ORIGIN,
                    "SESSION_COOKIE_SECURE": "true",
                }
            ),
            base_url=ORIGIN,
        ) as client:
            client.cookies.update(cookie)
            assert client.get(f"/api/reports/{report['id']}").json() == report
            assert client.get("/api/readiness").json()["schemaVersion"] == "0007_phase4_policy"


def test_migration_missing_employee_fails_atomically(postgres):
    with isolated_database(os.environ["TEST_DATABASE_URL"]) as (url, engine):
        with TestClient(
            create_app(
                {
                    "DATABASE_URL": url,
                    "UNLOOP_TEST_SCHEMA": isolated_schema(engine),
                    "APP_ORIGIN": ORIGIN,
                    "SESSION_COOKIE_SECURE": "true",
                }
            ),
            base_url=ORIGIN,
        ) as client:
            seed_report(client)
        with engine.begin() as connection:
            command.downgrade(migration_config(connection), "0001_phase1a")
            connection.execute(
                text(
                    "UPDATE reports SET employee_profile_id="
                    "(SELECT id FROM demo_profiles WHERE persona='manager')"
                )
            )
            connection.execute(text("DELETE FROM demo_profiles WHERE persona='employee'"))
        with pytest.raises(IntegrityError), engine.begin() as connection:
            command.upgrade(migration_config(connection), "head")
        with engine.connect() as connection:
            assert (
                connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_phase1a"
            )
            assert connection.scalar(text("SELECT count(*) FROM reports")) == 1
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM information_schema.columns "
                        "WHERE table_schema=current_schema() AND "
                        "table_name='reports' AND column_name='employee_persona'"
                    )
                )
                == 0
            )


def test_read_requests_do_not_wait_for_a_mutation_owner_lock(client, postgres):
    """Polling reads cannot occupy the whole thread pool waiting on one session lock."""
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from unloop.models import DemoSession

    assert (
        client.post("/api/session", json={}, headers={"Origin": "https://testserver"}).status_code
        == 201
    )
    with Session(postgres[1]) as db, db.begin():
        db.scalar(select(DemoSession).with_for_update())
        with ThreadPoolExecutor(max_workers=4) as pool:
            reads = [pool.submit(client.get, "/api/session") for _ in range(4)]
            for read in reads:
                assert read.result(timeout=2).status_code == 200


def test_polling_burst_completes_without_pool_thread_starvation(client):
    from concurrent.futures import ThreadPoolExecutor

    assert (
        client.post("/api/session", json={}, headers={"Origin": "https://testserver"}).status_code
        == 201
    )
    with ThreadPoolExecutor(max_workers=32) as pool:
        reads = [pool.submit(client.get, "/api/session") for _ in range(64)]
        for read in reads:
            assert read.result(timeout=5).status_code == 200
