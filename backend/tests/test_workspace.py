import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session
from unloop import create_app
from unloop.models import DemoProfile, DemoSession, Report

from scripts.postgres_test_support import ROOT, migrate

ORIGIN = "https://testserver"
MESSAGE = "Prepare my London expense report for 1–4 October 2026 for a client workshop."
HEADER = {
    "name": "London expense report",
    "startDate": "2026-10-01",
    "endDate": "2026-10-04",
    "businessPurpose": "a client workshop",
}


def start(client):
    response = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
    assert response.status_code in {200, 201}
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["csrfToken"]}


def propose(client, headers):
    response = client.post("/api/report-proposals", json={"message": MESSAGE}, headers=headers)
    assert response.status_code == 200
    return response.json()


def confirmation(proposal, **changes):
    return {
        "proposalToken": proposal["proposalToken"],
        "confirmed": True,
        "header": {**HEADER, **changes},
    }


def test_session_cookie_and_seeded_profiles(client, postgres):
    response = client.post("/api/session", json={}, headers={"Origin": ORIGIN})
    assert response.status_code == 201
    cookie = response.headers["set-cookie"]
    assert all(
        part in cookie
        for part in ["HttpOnly", "Secure", "SameSite=lax", "Max-Age=28800", "expires=", "Path=/"]
    )
    token = client.cookies.get("unloop_demo")
    assert len(token) == 43 and token not in str(response.json())
    assert response.json()["profile"]["grade"] == "C"
    assert response.headers["cache-control"] == "no-store"
    with Session(postgres[1]) as db:
        owner = db.scalar(select(DemoSession))
        assert owner.token_hash == hashlib.sha256(token.encode()).hexdigest()
        assert owner.expires_at - owner.created_at == timedelta(hours=8)
        assert {(p.persona, p.grade) for p in db.scalars(select(DemoProfile))} == {
            ("employee", "C"),
            ("manager", None),
        }
    assert client.get("/api/session").json()["persona"] == "employee"
    assert client.post("/api/session", json={}, headers={"Origin": ORIGIN}).status_code == 200


def test_missing_invalid_and_expired_sessions(client, postgres):
    assert client.get("/api/reports").status_code == 401
    client.cookies.set("unloop_demo", "forged")
    assert client.get("/api/session").json()["error"]["code"] == "invalid_session"
    client.cookies.clear()
    headers = start(client)
    proposal = propose(client, headers)
    with Session(postgres[1]) as db, db.begin():
        owner = db.scalar(select(DemoSession))
        owner.created_at = datetime.now(UTC) - timedelta(hours=9)
        owner.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    expired = client.post("/api/reports", json=confirmation(proposal), headers=headers)
    assert expired.status_code == 401
    assert expired.json()["error"]["code"] == "session_expired"
    assert "Max-Age=0" in expired.headers["set-cookie"]
    assert client.get("/api/reports").status_code == 401
    with Session(postgres[1]) as db:
        assert db.scalar(select(func.count()).select_from(Report)) == 0


def test_valid_length_fabricated_cookie_is_rejected(client):
    client.cookies.set("unloop_demo", "x" * 43)
    assert client.get("/api/reports").json()["error"]["code"] == "invalid_session"


def test_proposal_is_not_a_report_then_confirmation_persists(client, postgres):
    headers = start(client)
    proposal = propose(client, headers)
    assert proposal["header"] == HEADER
    assert proposal["parser"] == "deterministic-v1"
    assert client.get("/api/reports").json() == {"reports": []}
    with Session(postgres[1]) as db:
        assert db.scalar(select(func.count()).select_from(Report)) == 0
    confirmed = client.post(
        "/api/reports", json=confirmation(proposal, name="Reviewed London visit"), headers=headers
    )
    assert confirmed.status_code == 201
    report = confirmed.json()
    assert report["name"] == "Reviewed London visit"
    assert client.get(f"/api/reports/{report['id']}").json() == report
    assert client.get("/api/reports").json()["reports"] == [report]
    assert "manager" not in str(proposal).lower()
    assert not any(
        "manager" in column["name"] for column in inspect(postgres[1]).get_columns("reports")
    )


def test_isolation_and_proposal_cannot_cross_sessions(client, app_config):
    headers_a = start(client)
    proposal = propose(client, headers_a)
    report = client.post("/api/reports", json=confirmation(proposal), headers=headers_a).json()
    with TestClient(create_app(app_config), base_url=ORIGIN) as other:
        headers_b = start(other)
        assert other.get("/api/reports").json() == {"reports": []}
        assert other.get(f"/api/reports/{report['id']}").status_code == 404
        assert (
            other.post("/api/reports", json=confirmation(proposal), headers=headers_b).status_code
            == 400
        )
        assert (
            other.post(
                "/api/report-proposals", json={"message": MESSAGE}, headers=headers_a
            ).status_code
            == 403
        )


def test_manager_visibility_and_client_persona_spoofing(client):
    headers = start(client)
    proposal = propose(client, headers)
    report = client.post("/api/reports", json=confirmation(proposal), headers=headers).json()
    response = client.patch("/api/session/persona", json={"persona": "manager"}, headers=headers)
    assert response.status_code == 200
    assert "grade" not in response.json()["profile"]
    assert client.get("/api/reports").json() == {"reports": []}
    spoof = {**headers, "X-Persona": "employee", "X-Employee-Grade": "G"}
    assert client.get(f"/api/reports/{report['id']}", headers=spoof).status_code == 403
    assert (
        client.post("/api/report-proposals", json={"message": MESSAGE}, headers=spoof).status_code
        == 403
    )
    assert (
        client.post("/api/reports", json=confirmation(proposal), headers=spoof).status_code == 403
    )
    assert (
        client.patch(
            "/api/session/persona", json={"persona": "employee"}, headers=headers
        ).status_code
        == 200
    )
    assert client.get(f"/api/reports/{report['id']}").status_code == 200
    assert client.get("/api/session").json()["profile"]["grade"] == "C"


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://attacker.invalid"},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    ],
)
def test_session_bootstrap_rejects_cross_site(client, headers):
    assert client.post("/api/session", json={}, headers=headers).status_code == 403


@pytest.mark.parametrize(
    "path, method, body",
    [
        ("/api/session/persona", "PATCH", {"persona": "manager"}),
        ("/api/report-proposals", "POST", {"message": MESSAGE}),
    ],
)
def test_all_mutations_require_csrf_and_origin(client, path, method, body):
    headers = start(client)
    assert client.request(method, path, json=body, headers={"Origin": ORIGIN}).status_code == 403
    assert (
        client.request(
            method, path, json=body, headers={"X-CSRF-Token": headers["X-CSRF-Token"]}
        ).status_code
        == 403
    )
    assert (
        client.request(
            method, path, json=body, headers={**headers, "X-CSRF-Token": "wrong"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"persona": "employee", "grade": "G"},
        {"persona": "admin"},
        {"persona": "employee", "employeeId": "fake"},
    ],
)
def test_identity_or_grade_edit_is_rejected(client, extra):
    headers = start(client)
    assert client.patch("/api/session/persona", json=extra, headers=headers).status_code == 422
    assert client.get("/api/session").json()["profile"]["grade"] == "C"


@pytest.mark.parametrize(
    "changes",
    [
        {"startDate": ""},
        {"startDate": "10-01"},
        {"startDate": "2026-02-30"},
        {"startDate": "2026-10-05"},
        {"endDate": "04 October"},
        {"businessPurpose": "   "},
        {"businessPurpose": "a"},
        {"businessPurpose": "x" * 501},
        {"name": ""},
        {"managerEmail": "manager@example.com"},
        {"grade": "G"},
    ],
)
def test_invalid_confirmed_headers_are_rejected_without_report(client, changes):
    headers = start(client)
    proposal = propose(client, headers)
    response = client.post("/api/reports", json=confirmation(proposal, **changes), headers=headers)
    assert response.status_code == 422
    assert client.get("/api/reports").json() == {"reports": []}


@pytest.mark.parametrize("confirmed", [False, "true", 1, None])
def test_no_implicit_confirmation(client, confirmed):
    headers = start(client)
    proposal = propose(client, headers)
    body = {**confirmation(proposal), "confirmed": confirmed}
    assert client.post("/api/reports", json=body, headers=headers).status_code == 422
    assert client.get("/api/reports").json() == {"reports": []}


def test_confirmation_csrf_replay_and_changed_payload(client):
    headers = start(client)
    proposal = propose(client, headers)
    payload = confirmation(proposal)
    assert client.post("/api/reports", json=payload, headers={"Origin": ORIGIN}).status_code == 403
    first = client.post("/api/reports", json=payload, headers=headers)
    again = client.post("/api/reports", json=payload, headers=headers)
    assert first.status_code == 201 and again.status_code == 200
    assert first.json()["id"] == again.json()["id"]
    assert (
        client.post(
            "/api/reports", json=confirmation(proposal, name="Changed visit"), headers=headers
        ).status_code
        == 409
    )
    assert len(client.get("/api/reports").json()["reports"]) == 1


def test_concurrent_confirmation_creates_one_report(client):
    headers = start(client)
    payload = confirmation(propose(client, headers))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: client.post("/api/reports", json=payload, headers=headers), range(2))
        )
    assert sorted(r.status_code for r in results) == [200, 201]
    assert results[0].json()["id"] == results[1].json()["id"]
    assert len(client.get("/api/reports").json()["reports"]) == 1


def test_expired_or_forged_proposals(client, monkeypatch):
    headers = start(client)
    proposal = propose(client, headers)
    forged = {**confirmation(proposal), "proposalToken": "forged" * 8}
    assert client.post("/api/reports", json=forged, headers=headers).status_code == 400
    monkeypatch.setattr("unloop.api.PROPOSAL_TTL_SECONDS", -1)
    assert (
        client.post("/api/reports", json=confirmation(proposal), headers=headers).status_code == 409
    )
    assert client.get("/api/reports").json() == {"reports": []}


def test_database_reopen_after_new_app_instance(client, app_config):
    headers = start(client)
    proposal = propose(client, headers)
    cookies = dict(client.cookies)
    # A fresh app/engine must honor the DB-owned session and stateless proposal.
    with TestClient(create_app(app_config), base_url=ORIGIN) as restarted:
        restarted.cookies.update(cookies)
        report = restarted.post("/api/reports", json=confirmation(proposal), headers=headers).json()
        assert restarted.get(f"/api/reports/{report['id']}").json() == report
        assert restarted.get("/api/reports").json()["reports"] == [report]
    assert client.get(f"/api/reports/{report['id']}").json() == report


def test_actual_migration_is_repeatable_and_matches_models(postgres):
    _url, engine = postgres
    migrate(engine)
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "documents",
        "document_bytes",
        "evidence_links",
        "evidence_jobs",
        "gmail_connections",
        "gmail_oauth_states",
        "gmail_scans",
        "gmail_imports",
        "demo_sessions",
        "demo_profiles",
        "reports",
    }
    config = Config(str(ROOT / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)


def test_json_and_bounded_body_contract(client):
    headers = start(client)
    assert client.post("/api/report-proposals", content="{}", headers=headers).status_code == 415
    assert (
        client.post(
            "/api/report-proposals", json={"message": "x" * 17000}, headers=headers
        ).status_code
        == 413
    )


def test_readiness_checks_migrated_storage(client):
    assert client.get("/api/readiness").json()["database"] == "ready"
