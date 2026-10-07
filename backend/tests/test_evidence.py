"""Real PostgreSQL evidence, ownership, migration and worker recovery regressions."""

import io
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from PIL import Image
from pypdf import PdfWriter
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from unloop import create_app
from unloop.evidence_validation import MAX_BYTES, InvalidDocument, validate_bytes
from unloop.models import Document, DocumentBytes, EvidenceJob, EvidenceLink
from unloop.worker import claim_job, finish_job, run_once

from backend.tests.test_hardening import migration_config
from scripts.postgres_test_support import isolated_database

ORIGIN = "https://testserver"


def image_bytes(format="PNG"):
    stream = io.BytesIO()
    Image.new("RGB", (48, 32), (200, 120, 20)).save(stream, format=format)
    return stream.getvalue()


def pdf_bytes(pages=1, encrypted=False):
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=200, height=300)
    if encrypted:
        writer.encrypt("synthetic-password")
    stream = io.BytesIO()
    writer.write(stream)
    return stream.getvalue()


def report_and_headers(client):
    session = client.post("/api/session", json={}, headers={"Origin": ORIGIN}).json()
    headers = {"Origin": ORIGIN, "X-CSRF-Token": session["csrfToken"]}
    proposal = client.post(
        "/api/report-proposals",
        headers=headers,
        json={"message": "London 1–4 October 2026 for a client workshop"},
    ).json()
    report = client.post(
        "/api/reports",
        headers=headers,
        json={
            "proposalToken": proposal["proposalToken"],
            "header": proposal["header"],
            "confirmed": True,
        },
    ).json()
    return report["id"], headers


def upload(
    client,
    report,
    headers,
    *,
    content=None,
    mime="image/png",
    source="workspace",
    name="receipt.png",
):
    return client.post(
        f"/api/reports/{report}/evidence",
        headers=headers,
        data={"source": source},
        files={"files": (name, image_bytes() if content is None else content, mime)},
    )


def docs(client, report):
    response = client.get(f"/api/reports/{report}/evidence")
    assert response.status_code == 200
    return response.json()["documents"]


@pytest.mark.parametrize(
    "content,mime,pages",
    [
        (image_bytes(), "image/png", 1),
        (image_bytes("JPEG"), "image/jpeg", 1),
        (pdf_bytes(10), "application/pdf", 10),
    ],
)
def test_bytes_retained_separate_list_rows_and_reopen(
    client, app_config, postgres, content, mime, pages
):
    report, headers = report_and_headers(client)
    result = upload(
        client, report, headers, content=content, mime=mime, name="../../bad\r\nname.exe"
    )
    assert result.status_code == 201
    item = docs(client, report)[0]
    assert item["state"] == "queued" and item["pageCount"] == pages
    assert item["filename"].endswith(
        {"image/png": ".png", "image/jpeg": ".jpg", "application/pdf": ".pdf"}[mime]
    )
    assert "/" not in item["filename"] and "\r" not in item["filename"]
    assert "content" not in item and "sha256" not in item
    response = client.get(item["originalUrl"])
    assert response.content == content and response.headers["x-content-type-options"] == "nosniff"
    assert "attachment" in response.headers["content-disposition"]
    with postgres[1].connect() as db:
        assert db.scalar(select(DocumentBytes.content)) == content
    with TestClient(create_app(app_config), base_url=ORIGIN) as reopened:
        reopened.cookies.update(dict(client.cookies))
        assert reopened.get(item["originalUrl"]).content == content
    assert run_once(postgres[1])
    assert docs(client, report)[0]["state"] == "validated"
    assert not run_once(postgres[1])


@pytest.mark.parametrize(
    "content,mime,code",
    [
        (b"", "image/png", "document_size"),
        (b"x" * (MAX_BYTES + 1), "image/png", "document_size"),
        (image_bytes(), "image/jpeg", "document_type"),
        (b"<svg></svg>", "image/png", "document_type"),
        (b"\x89PNG\r\n\x1a\ntruncated", "image/png", "invalid_document"),
        (image_bytes("JPEG")[:30], "image/jpeg", "invalid_document"),
        (b"%PDF-1.7\ntruncated", "application/pdf", "invalid_document"),
        (pdf_bytes(11), "application/pdf", "document_pages"),
        (pdf_bytes(encrypted=True), "application/pdf", "encrypted_pdf"),
    ],
)
def test_invalid_files_leave_no_bytes_links_or_jobs(client, postgres, content, mime, code):
    report, headers = report_and_headers(client)
    result = upload(client, report, headers, content=content, mime=mime)
    assert result.status_code == 422 and result.json()["error"]["code"] == code
    assert docs(client, report) == []
    with postgres[1].connect() as db:
        for model in (Document, DocumentBytes, EvidenceLink, EvidenceJob):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_bad_batch_is_atomic_and_ten_file_limit(client):
    report, headers = report_and_headers(client)
    files = [
        ("files", ("good.png", image_bytes(), "image/png")),
        ("files", ("bad.png", b"bad", "image/png")),
    ]
    assert (
        client.post(
            f"/api/reports/{report}/evidence", headers=headers, data={"source": "chat"}, files=files
        ).status_code
        == 422
    )
    assert docs(client, report) == []
    files = [("files", (f"{i}.png", image_bytes(), "image/png")) for i in range(11)]
    assert (
        client.post(
            f"/api/reports/{report}/evidence", headers=headers, data={"source": "chat"}, files=files
        ).status_code
        == 422
    )
    response = client.post(
        f"/api/reports/{report}/evidence",
        headers=headers,
        data={"source": "chat"},
        files=files[:10],
    )
    assert response.status_code == 201 and len(response.json()["documents"]) == 10
    assert len(docs(client, report)) == 1


def test_chat_workspace_cross_report_dedup_has_provenance(client, postgres):
    report, headers = report_and_headers(client)
    first = upload(client, report, headers, source="chat").json()["documents"][0]
    second = upload(client, report, headers).json()["documents"][0]
    another, _ = report_and_headers(client)
    third = upload(client, another, headers).json()["documents"][0]
    assert first["id"] == second["id"] == third["id"]
    assert not first["duplicate"] and second["duplicate"] and third["duplicate"]
    assert docs(client, report)[0]["sources"] == ["chat", "workspace"]
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Document)) == 1
        assert db.scalar(select(func.count()).select_from(EvidenceJob)) == 1
        assert db.scalar(select(func.count()).select_from(EvidenceLink)) == 3


def test_owner_persona_csrf_origin_and_private_hash(client, app_config):
    report, headers = report_and_headers(client)
    assert upload(client, report, {"Origin": ORIGIN}).status_code == 403
    assert upload(client, report, {**headers, "Origin": "https://evil.example"}).status_code == 403
    assert upload(client, report, headers, source="gmail").status_code == 422
    item = upload(client, report, headers).json()["documents"][0]
    with TestClient(create_app(app_config), base_url=ORIGIN) as other:
        own_report, own_headers = report_and_headers(other)
        assert other.get(f"/api/reports/{report}/evidence").status_code == 404
        assert other.get(f"/api/documents/{item['id']}/original").status_code == 404
        assert (
            other.post(
                f"/api/documents/{item['id']}/retry", json={}, headers=own_headers
            ).status_code
            == 404
        )
        response = upload(other, own_report, own_headers).json()["documents"][0]
        assert not response["duplicate"] and response["id"] != item["id"]
    client.patch("/api/session/persona", json={"persona": "manager"}, headers=headers)
    assert client.get(f"/api/documents/{item['id']}/original").status_code == 403
    assert client.get(f"/api/reports/{report}/evidence").status_code == 403
    assert upload(client, report, headers).status_code == 403
    assert (
        client.post(f"/api/documents/{item['id']}/retry", json={}, headers=headers).status_code
        == 403
    )


def test_concurrent_same_owner_uploads_share_one_job(client, app_config, postgres):
    report, headers = report_and_headers(client)
    cookie = dict(client.cookies)

    def send():
        with TestClient(create_app(app_config), base_url=ORIGIN) as concurrent:
            concurrent.cookies.update(cookie)
            response = upload(concurrent, report, headers)
            assert response.status_code == 201
            return response.json()["documents"][0]["id"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert len(set(pool.map(lambda _: send(), range(2)))) == 1
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(EvidenceJob)) == 1


def test_worker_crash_expired_lease_reclaim_and_idempotent_finish(client, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    engine, now = postgres[1], datetime.now(UTC)
    first = claim_job(engine, now=now)
    assert first and not claim_job(engine, now=now + timedelta(seconds=1))
    reclaimed = claim_job(engine, now=now + timedelta(seconds=31))
    assert reclaimed.id == first.id and reclaimed.token != first.token
    assert not finish_job(engine, first, now=now + timedelta(seconds=32))
    assert finish_job(engine, reclaimed, now=now + timedelta(seconds=32))
    assert not finish_job(engine, reclaimed, now=now + timedelta(seconds=33))
    assert docs(client, report)[0]["state"] == "validated"
    assert docs(client, report)[0]["job"]["attempts"] == 2


def test_stale_revision_result_does_not_replace_current_document(client, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    engine = postgres[1]
    claim = claim_job(engine)
    with Session(engine) as db, db.begin():
        document = db.get(Document, claim.document_id)
        document.revision += 1
        document.state = "queued"
    assert finish_job(engine, claim)
    assert docs(client, report)[0]["state"] == "queued"
    with Session(engine) as db:
        assert db.get(EvidenceJob, claim.id).failure_code == "stale_revision"


def test_bounded_attempts_exhaustion_and_explicit_retry_revision(client, postgres):
    report, headers = report_and_headers(client)
    item = upload(client, report, headers).json()["documents"][0]
    engine, now = postgres[1], datetime.now(UTC)
    for _attempt in range(3):
        claim = claim_job(engine, now=now)
        assert claim
        assert finish_job(engine, claim, failure="validation_timeout", transient=True, now=now)
        now += timedelta(seconds=10)
    assert docs(client, report)[0]["state"] == "failed"
    result = client.post(f"/api/documents/{item['id']}/retry", headers=headers, json={})
    assert result.status_code == 200 and result.json()["revision"] == 2
    assert (
        client.post(f"/api/documents/{item['id']}/retry", headers=headers, json={}).status_code
        == 409
    )
    assert run_once(engine)
    assert docs(client, report)[0]["state"] == "validated"
    with engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(DocumentBytes)) == 1
        assert db.scalar(select(func.count()).select_from(EvidenceJob)) == 2


def test_crashed_last_attempt_becomes_failed(client, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    engine, now = postgres[1], datetime.now(UTC)
    for _ in range(3):
        assert claim_job(engine, now=now)
        now += timedelta(seconds=31)
    assert claim_job(engine, now=now) is None
    assert docs(client, report)[0]["failureCode"] == "attempts_exhausted"


def test_worker_integrity_error_retains_original(client, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    with Session(postgres[1]) as db, db.begin():
        document = db.scalar(select(Document))
        document.sha256 = "0" * 64
    assert run_once(postgres[1])
    item = docs(client, report)[0]
    assert item["state"] == "failed" and item["failureCode"] == "integrity_failed"
    assert client.get(item["originalUrl"]).content == image_bytes()


def test_worker_timeout_is_retryable_and_sanitized(client, postgres, monkeypatch):
    from unloop import worker

    report, headers = report_and_headers(client)
    upload(client, report, headers)

    def timeout(*args):
        raise InvalidDocument("validation_timeout")

    monkeypatch.setattr(worker, "bounded_validation", timeout)
    assert run_once(postgres[1])
    item = docs(client, report)[0]
    assert item["state"] == "queued" and item["failureCode"] == "validation_timeout"


def test_expired_session_jobs_never_validate(client, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    with postgres[1].begin() as db:
        db.execute(
            text(
                "UPDATE demo_sessions SET created_at=now()-interval '2 days', "
                "expires_at=now()-interval '1 day'"
            )
        )
    assert not run_once(postgres[1])
    with Session(postgres[1]) as db:
        assert db.scalar(select(Document)).failure_code == "session_expired"


def test_database_owner_constraints_reject_foreign_links(client, app_config, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    with TestClient(create_app(app_config), base_url=ORIGIN) as other:
        report_and_headers(other)
        with Session(postgres[1]) as db:
            from unloop.models import Report

            foreign = db.scalar(select(Report).where(Report.id != report))
            document = db.scalar(select(Document))
            with pytest.raises(IntegrityError), db.begin_nested():
                db.add(
                    EvidenceLink(
                        id=uuid4(),
                        session_id=foreign.session_id,
                        report_id=foreign.id,
                        document_id=document.id,
                        source="chat",
                        filename="safe.png",
                        created_at=datetime.now(UTC),
                    )
                )
                db.flush()


def test_phase1b_fresh_upgrade_downgrade_reupgrade_alignment(postgres):
    with isolated_database(postgres[0]) as (_, engine):
        with engine.begin() as db:
            config = migration_config(db)
            command.check(config)
            command.downgrade(config, "0002_phase1a_hardening")
            assert db.scalar(text("SELECT to_regclass('documents')")) is None
            command.upgrade(config, "head")
            command.check(config)
            assert (
                db.scalar(text("SELECT version_num FROM alembic_version"))
                == "0003_phase1b_evidence"
            )


@pytest.mark.parametrize(
    "content,mime", [(image_bytes(), "image/png"), (pdf_bytes(), "application/pdf")]
)
def test_structural_validator_hashes_original_bytes(content, mime):
    import hashlib

    assert validate_bytes(content, mime)["sha256"] == hashlib.sha256(content).hexdigest()


def test_streamed_request_limit_does_not_trust_small_declared_length(client, monkeypatch):
    import unloop

    report, headers = report_and_headers(client)
    # Exercise the actual streaming boundary with a small cap rather than allocating 101 MiB.
    monkeypatch.setattr(unloop, "MAX_REQUEST_BYTES", 64)
    result = upload(client, report, {**headers, "Content-Length": "1"})
    assert result.status_code == 413
    assert docs(client, report) == []


def test_concurrent_workers_claim_only_once(client, postgres):
    report, headers = report_and_headers(client)
    upload(client, report, headers)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim_job(postgres[1]), range(2)))
    assert sum(claim is not None for claim in claims) == 1


def test_real_worker_process_crash_then_new_process_recovers(client, postgres):
    import os
    import subprocess
    import sys

    from scripts.postgres_test_support import isolated_schema

    report, headers = report_and_headers(client)
    upload(client, report, headers)
    env = {
        "PATH": os.environ.get("PATH", ""),
        "DATABASE_URL": postgres[0],
        "UNLOOP_TEST_SCHEMA": isolated_schema(postgres[1]),
    }
    # Abrupt OS-process exit after committing a lease: no final result/cleanup runs.
    code = (
        "import os; from unloop.database import Settings,postgres_engine; "
        "from unloop.worker import claim_job; s=Settings.load(); "
        "e=postgres_engine(s.database_url,schema=s.database_schema); "
        "assert claim_job(e); os._exit(7)"
    )
    crashed = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=10,
    )
    assert crashed.returncode == 7 and docs(client, report)[0]["state"] == "processing"
    with postgres[1].begin() as connection:
        connection.execute(text("UPDATE evidence_jobs SET lease_until=now()-interval '1 second'"))
    recovered = subprocess.run(
        [sys.executable, "-m", "unloop.worker", "--once"],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=25,
    )
    assert recovered.returncode == 0
    item = docs(client, report)[0]
    assert item["state"] == "validated" and item["job"]["attempts"] == 2


@pytest.mark.parametrize("change", ["none", "persona", "expiry"])
def test_upload_validation_releases_connection_and_rechecks_authority(
    client, postgres, monkeypatch, change
):
    from threading import Event

    import unloop.evidence as evidence
    from unloop.models import DemoSession

    report, headers = report_and_headers(client)
    entered, release = Event(), Event()
    validate = evidence.bounded_validation

    def delayed(content, mime):
        entered.set()
        assert release.wait(10)
        return validate(content, mime)

    monkeypatch.setattr(evidence, "bounded_validation", delayed)
    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = pool.submit(upload, client, report, headers)
        try:
            assert entered.wait(5)
            # A read using the usual session lock must complete while validation is held.
            assert pool.submit(client.get, "/api/reports").result(timeout=2).status_code == 200
            if change == "persona":
                response = pool.submit(
                    client.patch,
                    "/api/session/persona",
                    headers=headers,
                    json={"persona": "manager"},
                ).result(timeout=2)
                assert response.status_code == 200
            elif change == "expiry":
                with postgres[1].begin() as db:
                    db.execute(
                        DemoSession.__table__.update().values(
                            created_at=datetime.now(UTC) - timedelta(hours=1),
                            expires_at=datetime.now(UTC) - timedelta(seconds=1),
                        )
                    )
        finally:
            release.set()
        response = pending.result(timeout=10)
    assert response.status_code == {"none": 201, "persona": 403, "expiry": 401}[change]
    with postgres[1].connect() as db:
        for model in (Document, DocumentBytes, EvidenceLink, EvidenceJob):
            assert db.scalar(select(func.count()).select_from(model)) == (
                1 if change == "none" else 0
            )


def test_upload_content_type_error_is_multipart(client):
    report, headers = report_and_headers(client)
    response = client.post(f"/api/reports/{report}/evidence", headers=headers, json={})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "multipart_required"
