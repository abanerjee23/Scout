"""Real PostgreSQL lifecycle/storage with explicit fake Google adapter, not live proof."""

import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from urllib.parse import parse_qs, urlsplit

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from unloop import create_app
from unloop.gmail import active_token, cleanup_expired, run_scan_once
from unloop.gmail_provider import MAILBOX, GmailFailure, GmailSettings, GoogleAdapter
from unloop.models import (
    DemoSession,
    Document,
    DocumentBytes,
    EvidenceJob,
    GmailConnection,
    GmailImport,
    GmailOAuthState,
    GmailScan,
    Report,
)

from backend.tests.test_evidence import ORIGIN, image_bytes, report_and_headers


class FakeGoogle(GoogleAdapter):
    """Synthetic adapter injected only by tests; never enabled by environment flags."""

    def __init__(self, settings):
        super().__init__(settings)
        self.fail = None
        self.calls = []
        self.hook = None

    def tokens(self, **kwargs):
        self.calls.append(("tokens", kwargs))
        if self.hook:
            self.hook()
        return {
            "access_token": "synthetic-access",
            "refresh_token": "synthetic-refresh",
            "expires_at": datetime.now(UTC).timestamp() + 3600,
        }

    def profile(self, token):
        if self.fail == "wrong_account":
            raise GmailFailure("wrong_account")
        return MAILBOX

    def messages(self, token, start, end):
        self.calls.append(("messages", start, end))
        return ["message1", "message2"], False

    def message(self, token, id):
        self.calls.append(("message", id))
        if self.fail:
            raise GmailFailure(self.fail, self.fail == "provider_timeout")
        return datetime(2026, 10, 2, tzinfo=UTC), [
            {
                "id": "attachment1",
                "name": "synthetic.png",
                "mime": "image/png",
                "size": len(image_bytes()),
            }
        ]

    def attachment(self, token, message, attachment):
        self.calls.append(("attachment", message, attachment))
        if self.hook:
            self.hook()
        return image_bytes()

    def revoke(self, token):
        self.calls.append(("revoke",))


@pytest.fixture
def gmail_client(app_config):
    settings = {
        **app_config,
        "GOOGLE_CLIENT_ID": "public-test-client",
        "GOOGLE_CLIENT_SECRET": "synthetic-client-secret",
        "GMAIL_TOKEN_KEY_VERSION": "v1",
        "GMAIL_TOKEN_KEYS": json.dumps({"v1": Fernet.generate_key().decode()}),
    }
    app = create_app(settings)
    adapter = FakeGoogle(app.state.gmail_settings)
    app.state.gmail_adapter = adapter
    with TestClient(app, base_url=ORIGIN) as client:
        yield client, adapter, app.state.gmail_settings


def connected(value):
    client, adapter, settings = value
    report, headers = report_and_headers(client)
    response = client.post("/api/gmail/connect", json={}, headers=headers)
    state = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)["state"][0]
    callback = client.get(
        "/auth/google/callback",
        params={"state": state, "code": "synthetic-code"},
        follow_redirects=False,
    )
    assert callback.status_code == 303 and callback.headers["location"].endswith("gmail=connected")
    assert callback.headers["referrer-policy"] == "no-referrer"
    return report, headers, state


def scan(client, report, headers):
    disclosure = client.get(f"/api/reports/{report}/gmail-window").json()
    response = client.post(
        f"/api/reports/{report}/gmail-scans",
        headers=headers,
        json={"confirmed": True, "reportFingerprint": disclosure["reportFingerprint"]},
    )
    assert response.status_code == 201
    return response.json()["id"]


def test_oauth_encryption_single_use_ownership_and_no_implicit_scan(
    gmail_client, postgres, app_config
):
    client, adapter, settings = gmail_client
    report, headers, state = connected(gmail_client)
    assert client.get("/api/gmail").json()["account"] == MAILBOX
    with postgres[1].connect() as db:
        blob = db.scalar(select(GmailConnection.encrypted_tokens))
        assert b"synthetic-access" not in blob and b"synthetic-refresh" not in blob
        assert settings.decrypt(blob, "v1")["refresh_token"] == "synthetic-refresh"
        assert db.scalar(select(func.count()).select_from(GmailScan)) == 0
        assert db.scalar(select(GmailOAuthState.used)) is True
    replay = client.get(
        "/auth/google/callback",
        params={"state": state, "code": "synthetic-code"},
        follow_redirects=False,
    )
    assert replay.headers["location"].endswith("gmail=state_invalid")
    assert len([x for x in adapter.calls if x[0] == "tokens"]) == 1
    with TestClient(create_app(app_config), base_url=ORIGIN) as other:
        report_and_headers(other)
        assert other.get("/api/gmail").json()["account"] is None
        assert other.get(f"/api/reports/{report}/gmail-window").status_code == 404
    client.patch("/api/session/persona", headers=headers, json={"persona": "manager"})
    assert client.get("/api/gmail").status_code == 403
    assert client.post("/api/gmail/connect", headers=headers, json={}).status_code == 403


@pytest.mark.parametrize("failure", ["consent_denied", "wrong_account"])
def test_denied_wrong_account_and_csrf(gmail_client, postgres, failure):
    client, adapter, settings = gmail_client
    report, headers = report_and_headers(client)
    assert client.post("/api/gmail/connect", headers={"Origin": ORIGIN}, json={}).status_code == 403
    response = client.post("/api/gmail/connect", headers=headers, json={})
    state = parse_qs(urlsplit(response.json()["authorizationUrl"]).query)["state"][0]
    adapter.fail = failure
    params = (
        {"state": state, "error": "access_denied"}
        if failure == "consent_denied"
        else {"state": state, "code": "synthetic"}
    )
    result = client.get("/auth/google/callback", params=params, follow_redirects=False)
    assert result.headers["location"].endswith("gmail=" + failure)
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailConnection.encrypted_tokens)) is None


def test_scan_shared_bytes_provenance_reopen_and_repeated_dedup(gmail_client, postgres):
    client, adapter, settings = gmail_client
    report, headers, state = connected(gmail_client)
    disclosure = client.get(f"/api/reports/{report}/gmail-window").json()
    assert disclosure["windowStart"] == "2026-07-03T00:00:00+00:00"
    assert disclosure["windowEndExclusive"] == "2026-10-12T00:00:00+00:00"
    scan(client, report, headers)
    for _ in range(3):
        assert run_scan_once(postgres[1], settings, adapter)
    result = client.get(f"/api/reports/{report}/gmail-scans").json()["scans"][0]
    assert result["state"] == "complete" and result["imported"] == 2 and result["reviewRequired"]
    docs = client.get(f"/api/reports/{report}/evidence").json()["documents"]
    assert len(docs) == 1 and docs[0]["sources"] == ["gmail"]
    assert client.get(docs[0]["originalUrl"]).content == image_bytes()
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
        assert db.scalar(select(func.count()).select_from(EvidenceJob)) == 1
        assert db.scalar(select(func.count()).select_from(GmailImport)) == 2
        assert db.scalar(select(GmailImport.review_required)) is True
    scan(client, report, headers)
    for _ in range(3):
        run_scan_once(postgres[1], settings, adapter)
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
    assert (
        client.post("/api/gmail/disconnect", headers=headers, json={}).json()["providerRevocation"]
        == "revoked"
    )
    assert client.get(docs[0]["originalUrl"]).content == image_bytes()
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailConnection.encrypted_tokens)) is None


@pytest.mark.parametrize("change", ["persona", "expiry", "report", "disconnect"])
def test_delayed_attachment_rechecks_authority_without_locks(gmail_client, postgres, change):
    client, adapter, settings = gmail_client
    report, headers, state = connected(gmail_client)
    scan(client, report, headers)
    run_scan_once(postgres[1], settings, adapter)
    entered, release = Event(), Event()

    def pause():
        entered.set()
        assert release.wait(10)

    adapter.hook = pause
    with ThreadPoolExecutor(max_workers=2) as pool:
        future = pool.submit(run_scan_once, postgres[1], settings, adapter)
        try:
            assert entered.wait(5)
            assert pool.submit(client.get, "/api/reports").result(timeout=2).status_code == 200
            if change == "persona":
                assert (
                    pool.submit(
                        client.patch,
                        "/api/session/persona",
                        headers=headers,
                        json={"persona": "manager"},
                    )
                    .result(timeout=2)
                    .status_code
                    == 200
                )
            elif change == "disconnect":
                assert (
                    pool.submit(client.post, "/api/gmail/disconnect", headers=headers, json={})
                    .result(timeout=2)
                    .status_code
                    == 200
                )
            else:
                with postgres[1].begin() as db:
                    if change == "expiry":
                        db.execute(
                            DemoSession.__table__.update().values(
                                created_at=datetime.now(UTC) - timedelta(hours=1),
                                expires_at=datetime.now(UTC) - timedelta(seconds=1),
                            )
                        )
                    else:
                        db.execute(
                            Report.__table__.update().values(
                                business_purpose="Changed report purpose"
                            )
                        )
        finally:
            release.set()
        assert future.result(timeout=10)
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 0
        assert db.scalar(select(func.count()).select_from(EvidenceJob)) == 0


def test_refresh_rotation_disconnect_race_and_expiry_cleanup(gmail_client, postgres):
    client, adapter, settings = gmail_client
    report, headers, state = connected(gmail_client)
    with postgres[1].begin() as db:
        owner_id, version = db.execute(
            select(GmailConnection.session_id, GmailConnection.version)
        ).one()
        tokens = {"access_token": "old", "refresh_token": "refresh", "expires_at": 0}
        db.execute(
            GmailConnection.__table__.update().values(encrypted_tokens=settings.encrypt(tokens))
        )
    new = GmailSettings(
        settings.client_id,
        settings.client_secret,
        settings.callback,
        "v2",
        {"v1": settings.keys["v1"], "v2": Fernet.generate_key().decode()},
    )
    assert active_token(postgres[1], owner_id, version, new, adapter) == "synthetic-access"
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailConnection.key_version)) == "v2"
    with postgres[1].begin() as db:
        db.execute(GmailConnection.__table__.update().values(encrypted_tokens=new.encrypt(tokens)))
    adapter.hook = lambda: client.post("/api/gmail/disconnect", headers=headers, json={})
    with pytest.raises(GmailFailure, match="authorization_changed"):
        active_token(postgres[1], owner_id, version, new, adapter)
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailConnection.encrypted_tokens)) is None
    adapter.hook = None
    connected(gmail_client)
    with postgres[1].begin() as db:
        db.execute(
            DemoSession.__table__.update().values(
                created_at=datetime.now(UTC) - timedelta(hours=1),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
    cleanup_expired(postgres[1])
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailConnection.encrypted_tokens)) is None


def test_partial_checkpoint_retry_and_reclaim(gmail_client, postgres):
    client, adapter, settings = gmail_client
    report, headers, state = connected(gmail_client)
    scan(client, report, headers)
    run_scan_once(postgres[1], settings, adapter)
    run_scan_once(postgres[1], settings, adapter)
    adapter.fail = "provider_timeout"
    run_scan_once(postgres[1], settings, adapter)
    with postgres[1].begin() as db:
        assert db.scalar(select(GmailScan.cursor)) == 1
        assert db.scalar(select(GmailScan.imported)) == 1
        db.execute(GmailScan.__table__.update().values(available_at=datetime.now(UTC)))
    adapter.fail = None
    run_scan_once(postgres[1], settings, adapter)
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailScan.state)) == "complete"
        assert db.scalar(select(func.count()).select_from(GmailImport)) == 2


@pytest.mark.parametrize(
    "payload",
    [
        {"messages": "bad"},
        {"messages": [{"id": "../escape"}]},
        {"messages": [{"id": "same"}, {"id": "same"}]},
        {"messages": [{}]},
    ],
)
def test_provider_rejects_malformed_ids_without_reflecting_payload(monkeypatch, payload):
    adapter = GoogleAdapter(None)
    monkeypatch.setattr(adapter, "request", lambda *args, **kwargs: payload)
    with pytest.raises(GmailFailure, match="^invalid_provider_response$"):
        adapter.messages(
            "secret-token", datetime(2026, 7, 3, tzinfo=UTC), datetime(2026, 10, 12, tzinfo=UTC)
        )


def test_provider_scope_window_fixed_paths_and_byte_validation(monkeypatch):
    adapter = GoogleAdapter(None)
    calls = []

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return {"messages": [{"id": "abc"}], "nextPageToken": "unused"}

    monkeypatch.setattr(adapter, "request", request)
    start, end = datetime(2026, 7, 3, tzinfo=UTC), datetime(2026, 10, 12, tzinfo=UTC)
    assert adapter.messages("synthetic", start, end) == (["abc"], True)
    method, url, kwargs = calls[0]
    assert method == "GET" and url == "https://gmail.googleapis.com/gmail/v1/users/me/messages"
    assert kwargs["params"]["maxResults"] == 15
    assert f"after:{int(start.timestamp()) - 1}" in kwargs["params"]["q"]
    assert f"before:{int(end.timestamp())}" in kwargs["params"]["q"]
    monkeypatch.setattr(
        adapter, "request", lambda *args, **kwargs: {"data": "secret://invalid", "size": 12}
    )
    with pytest.raises(GmailFailure, match="^invalid_attachment$"):
        adapter.attachment("secret", "abc", "def")


@pytest.mark.parametrize(
    "mode",
    [
        "empty",
        "unsupported",
        "revoked",
        "permission_denied",
        "exhausted",
        "expired_consent",
        "changed_report",
    ],
)
def test_scan_distinct_terminal_or_retry_outcomes(gmail_client, postgres, mode):
    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    scan(client, report, headers)
    if mode == "empty":
        adapter.messages = lambda *args: ([], False)
    run_scan_once(postgres[1], settings, adapter)
    if mode == "empty":
        result = client.get(f"/api/reports/{report}/gmail-scans").json()["scans"][0]
        assert result["state"] == "complete" and result["failureCode"] == "empty"
        return
    if mode == "unsupported":
        adapter.message = lambda *args: (datetime(2026, 10, 2, tzinfo=UTC), [])
    if mode in {"revoked", "permission_denied"}:
        adapter.fail = mode
    if mode == "exhausted":
        adapter.fail = "provider_timeout"
    if mode in {"expired_consent", "changed_report"}:
        with postgres[1].begin() as db:
            if mode == "expired_consent":
                db.execute(
                    GmailScan.__table__.update().values(
                        expires_at=datetime.now(UTC) - timedelta(seconds=1)
                    )
                )
            else:
                db.execute(Report.__table__.update().values(business_purpose="Updated purpose"))
    for _ in range(4 if mode == "exhausted" else 2):
        with postgres[1].begin() as db:
            db.execute(GmailScan.__table__.update().values(available_at=datetime.now(UTC)))
        run_scan_once(postgres[1], settings, adapter)
    result = client.get(f"/api/reports/{report}/gmail-scans").json()["scans"][0]
    assert result["state"] == (
        "partial"
        if mode == "unsupported"
        else "cancelled"
        if mode in {"expired_consent", "changed_report"}
        else "failed"
    )
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 0
        if mode == "revoked":
            assert db.scalar(select(GmailConnection.encrypted_tokens)) is None
        if mode == "exhausted":
            assert db.scalar(select(GmailScan.attempts)) == 3


def test_gmail_migration_downgrade_reupgrade_preserves_manual_bytes(postgres, gmail_client):
    from alembic import command

    from backend.tests.test_hardening import migration_config

    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    scan(client, report, headers)
    for _ in range(3):
        run_scan_once(postgres[1], settings, adapter)
    with postgres[1].begin() as db:
        config = migration_config(db)
        command.check(config)
        command.downgrade(config, "0003_phase1b_evidence")
        assert db.scalar(select(DocumentBytes.content)) == image_bytes()
        command.upgrade(config, "head")
        command.check(config)
        assert db.scalar(select(func.count()).select_from(GmailConnection)) == 0


def test_provider_transport_errors_are_fixed_and_never_echo_credentials(monkeypatch):
    import httpx

    def fail(*args, **kwargs):
        raise httpx.ConnectError("postgresql://user:password@host?oauth_code=secret")

    monkeypatch.setattr(httpx.Client, "stream", fail)
    with pytest.raises(GmailFailure) as caught:
        GoogleAdapter(None).request(
            "GET", "https://gmail.googleapis.com/gmail/v1/users/me/profile", token="secret"
        )
    assert str(caught.value) == "provider_unavailable"
    assert str(GmailFailure("https://secret-password")) == "processing_failed"


@pytest.mark.parametrize("change", ["used", "expiry", "other_session"])
def test_oauth_state_guards_before_exchange(gmail_client, postgres, app_config, change):
    client, adapter, settings = gmail_client
    report, headers = report_and_headers(client)
    url = client.post("/api/gmail/connect", headers=headers, json={}).json()["authorizationUrl"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    if change != "other_session":
        with postgres[1].begin() as db:
            db.execute(
                GmailOAuthState.__table__.update().values(
                    **(
                        {"used": True}
                        if change == "used"
                        else {"expires_at": datetime.now(UTC) - timedelta(seconds=1)}
                    )
                )
            )
        result = client.get(
            "/auth/google/callback",
            params={"state": state, "code": "synthetic"},
            follow_redirects=False,
        )
    else:
        with TestClient(
            create_app(
                {
                    **app_config,
                    "GOOGLE_CLIENT_ID": settings.client_id,
                    "GOOGLE_CLIENT_SECRET": "synthetic",
                    "GMAIL_TOKEN_KEYS": json.dumps(settings.keys),
                    "GMAIL_TOKEN_KEY_VERSION": "v1",
                }
            ),
            base_url=ORIGIN,
        ) as other:
            report_and_headers(other)
            other.app.state.gmail_adapter = adapter
            result = other.get(
                "/auth/google/callback",
                params={"state": state, "code": "synthetic"},
                follow_redirects=False,
            )
    assert result.headers["location"].endswith("gmail=state_invalid")
    assert not adapter.calls


def test_storage_budget_is_atomic_and_dedup_still_reuses_existing(client, postgres, monkeypatch):
    import unloop.evidence as evidence

    from backend.tests.test_evidence import upload

    monkeypatch.setattr(evidence, "MAX_OWNER_DOCUMENTS", 1)
    report, headers = report_and_headers(client)
    assert upload(client, report, headers).status_code == 201
    assert upload(client, report, headers).json()["documents"][0]["duplicate"] is True
    assert (
        upload(client, report, headers, content=image_bytes("JPEG"), mime="image/jpeg").status_code
        == 409
    )
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
        assert db.scalar(select(func.count()).select_from(EvidenceJob)) == 1


def test_actual_scan_process_crash_reclaims_lease_without_duplicate_imports(gmail_client, postgres):
    import os
    import subprocess
    import sys

    from scripts.postgres_test_support import isolated_schema

    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    scan(client, report, headers)
    run_scan_once(postgres[1], settings, adapter)
    script = """
import os
from unloop.database import postgres_engine
from unloop.gmail import claim_scan
engine=postgres_engine(os.environ['DATABASE_URL'],schema=os.environ['UNLOOP_TEST_SCHEMA'])
assert claim_scan(engine) is not None
os._exit(7)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env={
            **os.environ,
            "DATABASE_URL": postgres[0],
            "UNLOOP_TEST_SCHEMA": isolated_schema(postgres[1]),
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    assert result.returncode == 7
    with postgres[1].begin() as db:
        assert db.scalar(select(GmailScan.state)) == "processing"
        db.execute(
            GmailScan.__table__.update().values(
                lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    assert run_scan_once(postgres[1], settings, adapter)
    assert run_scan_once(postgres[1], settings, adapter)
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailScan.state)) == "complete"
        assert db.scalar(select(func.count()).select_from(GmailImport)) == 2
        assert db.scalar(select(func.count()).select_from(Document)) == 1


def test_production_schema_transport_is_fail_closed(postgres):
    from sqlalchemy.exc import OperationalError
    from unloop.database import Settings, postgres_engine, validated_schema

    with pytest.raises(ValueError):
        validated_schema("unloop_app")
    with pytest.raises(ValueError):
        Settings.load(
            {
                "UNLOOP_ENV": "production",
                "APP_ORIGIN": "https://example.com",
                "DATABASE_SCHEMA": "public",
            }
        )
    with pytest.raises(ValueError):
        postgres_engine(postgres[0] + "?sslmode=disable", production=True)
    engine = postgres_engine(postgres[0], schema="unloop_app", production=True)
    try:
        with pytest.raises(OperationalError):
            with engine.connect():
                pass
    finally:
        engine.dispose()


def test_upload_concurrency_capacity_rejects_without_writes(client, postgres):
    from unloop.evidence import UPLOAD_SLOTS

    from backend.tests.test_evidence import upload

    report, headers = report_and_headers(client)
    acquired = []
    try:
        for _ in range(4):
            assert UPLOAD_SLOTS.acquire(blocking=False)
            acquired.append(True)
        assert upload(client, report, headers).json()["error"]["code"] == "upload_busy"
    finally:
        for _ in acquired:
            UPLOAD_SLOTS.release()
    assert upload(client, report, headers).status_code == 201


@pytest.mark.parametrize("mode", ["page_truncated", "ten_exact", "ten_with_more"])
def test_bounded_candidates_complete_before_accurate_truncation(gmail_client, postgres, mode):
    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    if mode == "page_truncated":
        adapter.messages = lambda *args: ([f"m{i}" for i in range(15)], True)
    else:
        adapter.messages = lambda *args: (["m0"], False)
        parts = [
            {
                "id": f"a{i}",
                "name": "synthetic.png",
                "mime": "image/png",
                "size": len(image_bytes()),
            }
            for i in range(11 if mode == "ten_with_more" else 10)
        ]
        adapter.message = lambda *args: (datetime(2026, 10, 2, tzinfo=UTC), parts)
    scan(client, report, headers)
    for _ in range(16):
        run_scan_once(postgres[1], settings, adapter)
    with postgres[1].connect() as db:
        count = db.scalar(select(GmailScan.cursor))
        # 10 file limit stops before uninspected later candidates; it must not stop at one.
        assert count == (10 if mode == "page_truncated" else 1)
        assert db.scalar(select(GmailScan.imported)) == 10
        assert db.scalar(select(GmailScan.truncated)) is (mode != "ten_exact")
        assert db.scalar(select(GmailScan.state)) == (
            "complete" if mode == "ten_exact" else "partial"
        )


@pytest.mark.parametrize(
    "tokens",
    [
        {},
        {"access_token": "x", "refresh_token": "y", "expires_at": "credential-secret"},
        {"access_token": "x", "refresh_token": "y", "expires_at": float("nan")},
        {"access_token": False, "refresh_token": "y", "expires_at": 0},
    ],
)
def test_malformed_encrypted_tokens_fail_closed(gmail_client, tokens):
    _, _, settings = gmail_client
    with pytest.raises(GmailFailure, match="^key_unavailable$"):
        settings.decrypt(settings.encrypt(tokens), "v1")


def test_stale_scan_retry_returns_recoverable_code(gmail_client, postgres):
    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    id = scan(client, report, headers)
    with postgres[1].begin() as db:
        db.execute(
            GmailScan.__table__.update().values(
                state="failed", expires_at=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    response = client.post(f"/api/gmail-scans/{id}/retry", headers=headers, json={})
    assert (
        response.status_code == 409 and response.json()["error"]["code"] == "authorization_changed"
    )


def test_search_truncation_processes_all_fifteen_ids_when_files_not_limit(gmail_client, postgres):
    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    adapter.messages = lambda *args: ([f"m{i}" for i in range(15)], True)
    adapter.message = lambda *args: (datetime(2026, 10, 2, tzinfo=UTC), [])
    scan(client, report, headers)
    for _ in range(16):
        assert run_scan_once(postgres[1], settings, adapter)
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailScan.cursor)) == 15
        assert db.scalar(select(GmailScan.truncated)) is True
        assert db.scalar(select(GmailScan.state)) == "partial"


@pytest.mark.parametrize("flag", [True, False, None, "missing"])
def test_actual_client_tls_flag(flag):
    from types import SimpleNamespace

    from unloop.database import verify_client_tls

    pgconn = SimpleNamespace() if flag == "missing" else SimpleNamespace(ssl_in_use=flag)
    connection = SimpleNamespace(
        info=SimpleNamespace(
            get_parameters=lambda: {"sslmode": "require", "gssencmode": "disable"}
        ),
        pgconn=pgconn,
    )
    if flag is True:
        verify_client_tls(connection)
    else:
        with pytest.raises(RuntimeError, match="^Client TLS (inactive|verification unavailable)$"):
            verify_client_tls(connection)


@pytest.mark.parametrize("change", ["disconnect", "expiry", "persona", "state_expiry"])
def test_callback_rechecks_before_profile(gmail_client, postgres, change, monkeypatch):
    client, adapter, _ = gmail_client
    _, headers = report_and_headers(client)
    url = client.post("/api/gmail/connect", headers=headers, json={}).json()["authorizationUrl"]
    state = parse_qs(urlsplit(url).query)["state"][0]
    profiles = []
    monkeypatch.setattr(adapter, "profile", lambda token: profiles.append(token))

    def revoke():
        if change == "disconnect":
            assert client.post("/api/gmail/disconnect", headers=headers, json={}).status_code == 200
        elif change == "state_expiry":
            with postgres[1].begin() as db:
                db.execute(
                    GmailOAuthState.__table__.update().values(
                        expires_at=datetime.now(UTC) - timedelta(seconds=1)
                    )
                )
        else:
            with postgres[1].begin() as db:
                values = (
                    {
                        "created_at": datetime.now(UTC) - timedelta(hours=1),
                        "expires_at": datetime.now(UTC) - timedelta(seconds=1),
                    }
                    if change == "expiry"
                    else {"active_persona": "manager"}
                )
                db.execute(DemoSession.__table__.update().values(**values))

    adapter.hook = revoke
    response = client.get(
        "/auth/google/callback",
        params={"state": state, "code": "synthetic"},
        follow_redirects=False,
    )
    assert not response.headers["location"].endswith("gmail=connected")
    assert profiles == []
    with postgres[1].connect() as db:
        assert db.scalar(select(GmailConnection.encrypted_tokens)) is None


def test_inline_original_provenance_dedup_reopen(gmail_client, postgres, app_config, monkeypatch):
    import base64

    client, adapter, _ = gmail_client
    report, headers, _ = connected(gmail_client)
    raw = image_bytes()
    requests = []

    def provider(method, url, **kwargs):
        requests.append((url, kwargs))
        return {
            "id": url.rsplit("/", 1)[-1],
            "internalDate": "1790899200000",
            "payload": {
                "parts": [
                    {
                        "partId": "0.1",
                        "filename": "receipt.png",
                        "mimeType": "image/png",
                        "body": {
                            "size": len(raw),
                            "data": base64.urlsafe_b64encode(raw).decode().rstrip("="),
                        },
                    },
                    {
                        "partId": "0.2",
                        "filename": "broken.png",
                        "mimeType": "image/png",
                        "body": {"size": 5, "data": "!bad!"},
                    },
                    {"filename": "bad.png", "mimeType": "image/png", "body": {}},
                    {"partId": "0.3", "mimeType": "text/plain", "body": {"data": "aGVsbG8"}},
                ]
            },
        }

    monkeypatch.setattr(adapter, "request", provider)
    monkeypatch.setattr(
        adapter, "message", lambda token, id: GoogleAdapter.message(adapter, token, id)
    )
    scan(client, report, headers)
    for _ in range(3):
        assert run_scan_once(postgres[1], client.app.state.gmail_settings, adapter)
    assert all(call[1]["limit"] == 57 * 1024 * 1024 for call in requests)
    assert not any(call[0] == "attachment" for call in adapter.calls)
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
        assert db.scalar(select(func.count()).select_from(GmailImport)) == 2
        assert set(db.scalars(select(GmailImport.attachment_id))) == {"inline:0.1"}
        assert db.scalar(select(GmailScan.state)) == "partial"
    import socket

    import httpx

    from backend.tests.test_process_restart import api_process

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # Reopen in two actual API OS processes, not an in-memory fixture response.
    for _ in range(2):
        with api_process(
            app_config["DATABASE_URL"], port, schema=app_config["UNLOOP_TEST_SCHEMA"]
        ) as origin:
            with httpx.Client(
                base_url=origin, headers={"Cookie": "unloop_demo=" + client.cookies["unloop_demo"]}
            ) as reopened:
                rows = reopened.get(f"/api/reports/{report}/evidence").json()["documents"]
                assert len(rows) == 1
                assert reopened.get(f"/api/documents/{rows[0]['id']}/original").content == raw


def test_inline_and_external_named_parts_over_fake_http(monkeypatch):
    import base64

    import httpx

    raw = image_bytes()
    payload = {
        "id": "message1",
        "internalDate": "1790899200000",
        "payload": {
            "parts": [
                {
                    "partId": "0.1",
                    "filename": "inline.png",
                    "mimeType": "image/png",
                    "body": {"size": len(raw), "data": base64.urlsafe_b64encode(raw).decode()},
                },
                {
                    "partId": "0.2",
                    "filename": "external.png",
                    "mimeType": "image/png",
                    "body": {"size": len(raw), "attachmentId": "real-id"},
                },
            ]
        },
    }
    original_client = httpx.Client
    paths = []

    def respond(request):
        paths.append(request.url.path)
        return httpx.Response(
            200,
            json=payload
            if request.url.path.endswith("message1")
            else payload["payload"]["parts"][0]["body"],
        )

    monkeypatch.setattr(
        httpx,
        "Client",
        lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs),
    )
    adapter = GoogleAdapter(None)
    _, parts = adapter.message("synthetic", "message1")
    inline = next(part for part in parts if part["id"] == "inline:0.1")
    from unloop.gmail_provider import decode_attachment

    assert decode_attachment(inline["data"], inline["size"]) == raw
    assert adapter.attachment("synthetic", "message1", "real-id") == raw
    assert paths == [
        "/gmail/v1/users/me/messages/message1",
        "/gmail/v1/users/me/messages/message1/attachments/real-id",
    ]


@pytest.mark.parametrize(
    "origin",
    [
        "https://user:pass@example.com",
        "https://example.com?secret=x",
        "https://example.com#fragment",
    ],
)
def test_origin_rejects_non_origin_components(origin):
    from unloop.database import Settings

    with pytest.raises(ValueError, match="APP_ORIGIN"):
        Settings.load({"APP_ORIGIN": origin})


def test_production_tls_diagnostics_redact_driver_failure():
    from types import SimpleNamespace

    from unloop.database import postgres_engine, verify_client_tls

    def fail():
        raise ValueError("postgresql://user:private-password@private-host/db")

    with pytest.raises(RuntimeError, match="^Client TLS verification unavailable$"):
        verify_client_tls(SimpleNamespace(info=SimpleNamespace(get_parameters=fail)))
    with pytest.raises(ValueError, match="TCP target"):
        postgres_engine("postgresql://user@/db", production=True)
