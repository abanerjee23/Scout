"""Session-owned OAuth and explicitly authorized durable Gmail scans."""

import hashlib
import secrets
import time as monotonic_time
from datetime import UTC, datetime, time, timedelta
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session

from unloop.api import ApiProblem, current_session, employee, mutation_session, resolve_session
from unloop.evidence import bounded_validation, own_report, persist_checked, safe_filename
from unloop.evidence_validation import InvalidDocument
from unloop.gmail_provider import MAILBOX, GmailFailure, decode_attachment
from unloop.models import (
    DemoSession,
    GmailConnection,
    GmailImport,
    GmailOAuthState,
    GmailScan,
    Report,
)

router = APIRouter()


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScanConsent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    confirmed: bool
    reportFingerprint: str


def fingerprint(report):
    return hashlib.sha256(
        f"{report.id}|{report.version}|{report.start_date}|{report.end_date}|{report.name}|{report.business_purpose}".encode()
    ).hexdigest()


def window(report):
    if (report.end_date - report.start_date).days + 1 > 31:
        raise ApiProblem(422, "report_duration", "Gmail scans support reports up to 31 days.")
    return (
        datetime.combine(report.start_date - timedelta(days=90), time.min, UTC),
        datetime.combine(report.end_date + timedelta(days=8), time.min, UTC),
    )


def initial_auth(request, *, mutation=False):
    if request.app.state.engine is None:
        raise ApiProblem(503, "database_unavailable", "Storage is unavailable.")
    with Session(request.app.state.engine) as db, db.begin():
        owner = resolve_session(request, db, lock=False)
        employee(owner)
        if mutation:
            mutation_session(request, owner)
        return owner.id


def configured(request):
    if request.app.state.gmail_settings is None:
        raise ApiProblem(
            503, "gmail_unconfigured", "Gmail is not configured. Manual uploads remain available."
        )
    return request.app.state.gmail_settings, request.app.state.gmail_adapter


def connection(db, owner):
    item = db.get(GmailConnection, owner.id)
    if item is None:
        item = GmailConnection(
            session_id=owner.id, version=uuid4(), credential_revision=1, status="disconnected"
        )
        db.add(item)
        db.flush()
    return item


def clear_connection(item, status="disconnected"):
    item.version = uuid4()
    item.credential_revision += 1
    item.encrypted_tokens = item.key_version = None
    item.status = status


def cleanup_expired(engine, *, now=None):
    now = now or datetime.now(UTC)
    with Session(engine) as db, db.begin():
        expired = select(DemoSession.id).where(DemoSession.expires_at <= now)
        db.execute(
            GmailConnection.__table__.update()
            .where(GmailConnection.session_id.in_(expired))
            .values(encrypted_tokens=None, key_version=None, status="disconnected", version=uuid4())
        )
        db.execute(
            delete(GmailOAuthState).where(
                or_(GmailOAuthState.session_id.in_(expired), GmailOAuthState.expires_at <= now)
            )
        )
        db.execute(
            GmailScan.__table__.update()
            .where(GmailScan.session_id.in_(expired), GmailScan.state.in_(["queued", "processing"]))
            .values(
                state="cancelled",
                failure_code="session_expired",
                lease_token=None,
                lease_until=None,
            )
        )


@router.get("/api/gmail")
def status(request: Request):
    initial_auth(request)
    with Session(request.app.state.engine) as db:
        owner = resolve_session(request, db, lock=False)
        employee(owner)
        item = db.get(GmailConnection, owner.id)
        return {
            "configured": request.app.state.gmail_settings is not None,
            "status": item.status if item else "disconnected",
            "account": item.mailbox if item and item.status == "connected" else None,
        }


@router.post("/api/gmail/connect")
def connect(body: Empty, request: Request):
    settings, adapter = configured(request)
    initial_auth(request, mutation=True)
    state = secrets.token_urlsafe(32)
    with Session(request.app.state.engine) as db, db.begin():
        owner = current_session(request, db)
        mutation_session(request, owner)
        employee(owner)
        item = connection(db, owner)
        # A new connect invalidates all pending states and in-flight token refreshes/scans.
        clear_connection(item)
        db.execute(delete(GmailOAuthState).where(GmailOAuthState.session_id == owner.id))
        db.add(
            GmailOAuthState(
                token_hash=hashlib.sha256(state.encode()).hexdigest(),
                session_id=owner.id,
                connection_version=item.version,
                expires_at=datetime.now(UTC) + timedelta(minutes=10),
                used=False,
            )
        )
    return {"authorizationUrl": adapter.authorization_url(state)}


@router.get("/auth/google/callback")
def callback(request: Request):
    settings, adapter = configured(request)
    state = request.query_params.get("state", "")
    outcome = "state_invalid"
    expected = None
    try:
        initial_auth(request)
        if len(state) != 43 or len(request.query_params.getlist("state")) != 1:
            raise GmailFailure("state_invalid")
        with Session(request.app.state.engine) as db, db.begin():
            owner = current_session(request, db)
            employee(owner)
            entry = db.scalar(
                select(GmailOAuthState)
                .where(GmailOAuthState.token_hash == hashlib.sha256(state.encode()).hexdigest())
                .with_for_update()
            )
            item = connection(db, owner)
            if (
                entry is None
                or entry.session_id != owner.id
                or entry.used
                or entry.expires_at <= datetime.now(UTC)
                or entry.connection_version != item.version
            ):
                raise GmailFailure("state_invalid")
            entry.used = True
            expected, owner_id, state_expiry = item.version, owner.id, entry.expires_at
        # Single-use state committed before any provider call. No DB transaction here.
        if request.query_params.get("error"):
            raise GmailFailure("consent_denied")
        codes = request.query_params.getlist("code")
        if len(codes) != 1 or not 1 <= len(codes[0]) <= 8192:
            raise GmailFailure("invalid_provider_response")
        tokens = adapter.tokens(code=codes[0])
        # Token exchange may outlive revocation or session/state authority.
        with Session(request.app.state.engine) as db:
            owner = resolve_session(request, db, lock=False)
            employee(owner)
            item = db.get(GmailConnection, owner.id)
            fresh_state = db.scalar(
                select(GmailOAuthState).where(
                    GmailOAuthState.token_hash == hashlib.sha256(state.encode()).hexdigest()
                )
            )
            if (
                owner.id != owner_id
                or item is None
                or item.version != expected
                or fresh_state is None
                or fresh_state.expires_at <= datetime.now(UTC)
                or state_expiry <= datetime.now(UTC)
            ):
                raise GmailFailure("connection_changed")
        mailbox = adapter.profile(tokens["access_token"])
        with Session(request.app.state.engine) as db, db.begin():
            owner = current_session(request, db)
            employee(owner)
            item = connection(db, owner)
            if (
                owner.id != owner_id
                or item.version != expected
                or state_expiry <= datetime.now(UTC)
            ):
                raise GmailFailure("connection_changed")
            item.encrypted_tokens, item.key_version = settings.encrypt(tokens), settings.key_version
            item.credential_revision += 1
            item.mailbox, item.status = mailbox, "connected"
        outcome = "connected"
    except GmailFailure as failure:
        outcome = failure.code
    except ApiProblem:
        outcome = "session_or_persona_changed"
    # Only fixed outcomes; never reflect codes/state/provider input. No callback access logs.
    return RedirectResponse(
        request.app.state.settings.app_origin + "/?gmail=" + outcome,
        status_code=303,
        headers={"Referrer-Policy": "no-referrer"},
    )


@router.post("/api/gmail/disconnect")
def disconnect(body: Empty, request: Request):
    initial_auth(request, mutation=True)
    token = None
    with Session(request.app.state.engine) as db, db.begin():
        owner = current_session(request, db)
        mutation_session(request, owner)
        employee(owner)
        item = connection(db, owner)
        if item.encrypted_tokens and request.app.state.gmail_settings:
            try:
                tokens = request.app.state.gmail_settings.decrypt(
                    item.encrypted_tokens, item.key_version
                )
                token = tokens.get("refresh_token") or tokens["access_token"]
            except GmailFailure:
                pass
        clear_connection(item)
        db.execute(delete(GmailOAuthState).where(GmailOAuthState.session_id == owner.id))
        db.execute(
            GmailScan.__table__.update()
            .where(GmailScan.session_id == owner.id, GmailScan.state.in_(["queued", "processing"]))
            .values(
                state="cancelled", failure_code="disconnected", lease_token=None, lease_until=None
            )
        )
    revoke = "not_available"
    if token:
        try:
            request.app.state.gmail_adapter.revoke(token)
            revoke = "revoked"
        except GmailFailure:
            revoke = "revocation_failed"
    return {"status": "disconnected", "providerRevocation": revoke, "evidenceRetained": True}


@router.get("/api/reports/{report_id}/gmail-window")
def disclose(report_id: UUID, request: Request):
    initial_auth(request)
    with Session(request.app.state.engine) as db:
        owner = resolve_session(request, db, lock=False)
        report = own_report(db, owner, report_id)
        start, end = window(report)
        return {
            "reportFingerprint": fingerprint(report),
            "windowStart": start.isoformat(),
            "windowEndExclusive": end.isoformat(),
            "lookbackDays": 90,
            "afterEndDays": 7,
            "maxMessages": 15,
            "maxFiles": 10,
            "maxBytes": 40 * 1024 * 1024,
            "permissionMinutes": 20,
        }


@router.post("/api/reports/{report_id}/gmail-scans", status_code=201)
def authorize_scan(report_id: UUID, body: ScanConsent, request: Request):
    configured(request)
    initial_auth(request, mutation=True)
    with Session(request.app.state.engine) as db, db.begin():
        owner = current_session(request, db)
        mutation_session(request, owner)
        report = own_report(db, owner, report_id)
        item = connection(db, owner)
        if item.status != "connected":
            raise ApiProblem(409, "reconnect_required", "Connect Gmail before authorizing a scan.")
        if not body.confirmed or body.reportFingerprint != fingerprint(report):
            raise ApiProblem(
                409,
                "scan_confirmation",
                "Review the current report window and explicitly authorize it.",
            )
        if (
            db.scalar(
                select(func.count()).select_from(GmailScan).where(GmailScan.session_id == owner.id)
            )
            >= 50
        ):
            raise ApiProblem(
                409,
                "scan_limit",
                "This demo session supports 50 scans; retained files remain available.",
            )
        now = datetime.now(UTC)
        start, end = window(report)
        scan = GmailScan(
            session_id=owner.id,
            report_id=report.id,
            report_fingerprint=fingerprint(report),
            connection_version=item.version,
            window_start=start,
            window_end=end,
            expires_at=now + timedelta(minutes=20),
            available_at=now,
            created_at=now,
        )
        db.add(scan)
        db.flush()
        return scan_view(scan)


def scan_view(scan):
    return {
        "id": str(scan.id),
        "reportId": str(scan.report_id),
        "state": scan.state,
        "scanned": scan.cursor,
        "imported": scan.imported,
        "skipped": scan.skipped,
        "truncated": scan.truncated,
        "failureCode": scan.failure_code,
        "expiresAt": scan.expires_at.isoformat(),
        "reviewRequired": True,
    }


@router.get("/api/reports/{report_id}/gmail-scans")
def scans(report_id: UUID, request: Request):
    initial_auth(request)
    with Session(request.app.state.engine) as db:
        owner = resolve_session(request, db, lock=False)
        own_report(db, owner, report_id)
        return {
            "scans": [
                scan_view(scan)
                for scan in db.scalars(
                    select(GmailScan)
                    .where(GmailScan.report_id == report_id, GmailScan.session_id == owner.id)
                    .order_by(GmailScan.created_at.desc())
                    .limit(10)
                )
            ]
        }


@router.post("/api/gmail-scans/{scan_id}/retry")
def retry(scan_id: UUID, body: Empty, request: Request):
    initial_auth(request, mutation=True)
    with Session(request.app.state.engine) as db, db.begin():
        owner = current_session(request, db)
        mutation_session(request, owner)
        employee(owner)
        item = connection(db, owner)
        scan = db.get(GmailScan, scan_id)
        if scan is None or scan.session_id != owner.id:
            raise ApiProblem(404, "not_found", "Scan not found.")
        assert_authority(db, scan, owner, item)
        if (
            scan.state not in {"partial", "failed"}
            or scan.attempts >= 3
            or (scan.message_ids is not None and scan.cursor >= len(scan.message_ids))
            or scan.imported >= 10
        ):
            raise ApiProblem(
                409,
                "new_consent_required",
                "Authorize a new bounded scan; previous files remain retained.",
            )
        scan.state, scan.failure_code, scan.available_at = "queued", None, datetime.now(UTC)
        return scan_view(scan)


def assert_authority(db, scan, owner, item):
    now = datetime.now(UTC)
    report = db.get(Report, scan.report_id)
    if (
        owner.expires_at <= now
        or owner.active_persona != "employee"
        or scan.expires_at <= now
        or item is None
        or item.status != "connected"
        or item.version != scan.connection_version
        or report is None
        or report.session_id != owner.id
        or fingerprint(report) != scan.report_fingerprint
    ):
        raise GmailFailure("authorization_changed")


def active_token(engine, owner_id, version, settings, adapter):
    with Session(engine) as db:
        owner = db.get(DemoSession, owner_id)
        item = db.get(GmailConnection, owner_id)
        if (
            owner is None
            or owner.expires_at <= datetime.now(UTC)
            or owner.active_persona != "employee"
            or item is None
            or item.status != "connected"
            or item.version != version
        ):
            raise GmailFailure("authorization_changed")
        revision, ciphertext, key = (
            item.credential_revision,
            item.encrypted_tokens,
            item.key_version,
        )
    tokens = settings.decrypt(ciphertext, key)
    needs_refresh = tokens.get("expires_at", 0) <= datetime.now(UTC).timestamp() + 30
    if needs_refresh:
        tokens = adapter.tokens(refresh=tokens.get("refresh_token"))
    if needs_refresh or key != settings.key_version:
        with Session(engine) as db, db.begin():
            owner = db.scalar(
                select(DemoSession).where(DemoSession.id == owner_id).with_for_update()
            )
            item = db.get(GmailConnection, owner_id)
            if (
                owner.expires_at <= datetime.now(UTC)
                or owner.active_persona != "employee"
                or item is None
                or item.version != version
                or item.status != "connected"
                or item.credential_revision != revision
            ):
                raise GmailFailure("authorization_changed")
            item.encrypted_tokens, item.key_version = settings.encrypt(tokens), settings.key_version
            item.credential_revision += 1
    return tokens["access_token"]


def claim_scan(engine):
    now = datetime.now(UTC)
    with Session(engine) as db, db.begin():
        scan = db.scalar(
            select(GmailScan)
            .where(
                or_(
                    and_(GmailScan.state == "queued", GmailScan.available_at <= now),
                    and_(GmailScan.state == "processing", GmailScan.lease_until <= now),
                )
            )
            .order_by(GmailScan.available_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if scan is None:
            return None
        if scan.attempts >= 3:
            scan.state, scan.failure_code = (
                "partial" if scan.imported else "failed",
                "attempts_exhausted",
            )
            scan.lease_token = scan.lease_until = None
            return None
        scan.state, scan.lease_token, scan.lease_until = (
            "processing",
            uuid4(),
            now + timedelta(seconds=360),
        )
        scan.attempts += 1
        db.flush()
        db.expunge(scan)
        return scan


def live_scan(db, claim):
    # Session lock first, same order as API persistence; no external calls in this transaction.
    owner = db.scalar(
        select(DemoSession).where(DemoSession.id == claim.session_id).with_for_update()
    )
    item = db.get(GmailConnection, claim.session_id)
    scan = db.scalar(select(GmailScan).where(GmailScan.id == claim.id).with_for_update())
    if (
        scan.state != "processing"
        or scan.lease_token != claim.lease_token
        or scan.lease_until <= datetime.now(UTC)
    ):
        raise GmailFailure("stale_lease")
    assert_authority(db, scan, owner, item)
    return scan, owner


def run_scan_once(engine, settings, adapter):
    cleanup_expired(engine)
    claim = claim_scan(engine)
    if claim is None:
        return False
    deadline = monotonic_time.monotonic() + 330
    try:
        with Session(engine) as db:
            owner, item = (
                db.get(DemoSession, claim.session_id),
                db.get(GmailConnection, claim.session_id),
            )
            assert_authority(db, claim, owner, item)
        token = active_token(engine, claim.session_id, claim.connection_version, settings, adapter)
        with Session(engine) as db:
            assert_authority(
                db,
                db.get(GmailScan, claim.id),
                db.get(DemoSession, claim.session_id),
                db.get(GmailConnection, claim.session_id),
            )
        if claim.message_ids is None:
            ids, truncated = adapter.messages(token, claim.window_start, claim.window_end)
            with Session(engine) as db, db.begin():
                scan, _owner = live_scan(db, claim)
                scan.message_ids, scan.truncated = ids, truncated
                scan.state = "queued" if ids else "complete"
                scan.failure_code = None if ids else "empty"
                scan.lease_token = scan.lease_until = None
                scan.attempts = 0
            return True
        if claim.cursor >= len(claim.message_ids):
            raise GmailFailure("invalid_checkpoint")
        message = claim.message_ids[claim.cursor]
        received, parts = adapter.message(token, message)
        if not claim.window_start <= received < claim.window_end:
            parts = []
        imported, consumed, skipped = claim.imported, claim.byte_count, 0
        bounded_out = False
        seen = set()
        for part in parts:
            if monotonic_time.monotonic() > deadline:
                raise GmailFailure("provider_timeout", True)
            identity = part["id"]
            if identity in seen:
                continue
            seen.add(identity)
            with Session(engine) as db:
                exists = db.scalar(
                    select(GmailImport.id).where(
                        GmailImport.scan_id == claim.id,
                        GmailImport.message_id == message,
                        GmailImport.attachment_id == identity,
                    )
                )
            if exists:
                continue
            if imported >= 10 or consumed + part["size"] > 40 * 1024 * 1024:
                bounded_out = True
                skipped += 1
                continue
            if (
                part["mime"] not in {"image/jpeg", "image/png", "application/pdf"}
                or not 0 < part["size"] <= 10 * 1024 * 1024
            ):
                skipped += 1
                continue
            # Recheck consent before each provider read, then again before every write.
            with Session(engine) as db:
                current = db.get(GmailScan, claim.id)
                assert_authority(
                    db,
                    current,
                    db.get(DemoSession, claim.session_id),
                    db.get(GmailConnection, claim.session_id),
                )
                imported, consumed = current.imported, current.byte_count
            try:
                content = (
                    decode_attachment(part["data"], part["size"])
                    if "data" in part
                    else adapter.attachment(token, message, identity)
                )
            except GmailFailure as failure:
                if failure.code not in {
                    "invalid_attachment",
                    "invalid_provider_response",
                    "provider_response_size",
                }:
                    raise
                skipped += 1
                continue
            if len(content) != part["size"] or consumed + len(content) > 40 * 1024 * 1024:
                skipped += 1
                continue
            try:
                info = bounded_validation(content, part["mime"])
            except InvalidDocument:
                skipped += 1
                continue
            with Session(engine) as db, db.begin():
                scan, owner = live_scan(db, claim)
                if scan.imported >= 10 or scan.byte_count + len(content) > 40 * 1024 * 1024:
                    raise GmailFailure("scan_limit")
                existing = db.scalar(
                    select(GmailImport.id).where(
                        GmailImport.scan_id == scan.id,
                        GmailImport.message_id == message,
                        GmailImport.attachment_id == identity,
                    )
                )
                if existing:
                    continue
                result = persist_checked(
                    db,
                    owner,
                    scan.report_id,
                    "gmail",
                    [(content, info, safe_filename(part["name"], info["mime_type"]))],
                )[0]
                db.add(
                    GmailImport(
                        session_id=owner.id,
                        scan_id=scan.id,
                        document_id=UUID(result["id"]),
                        mailbox=MAILBOX,
                        message_id=message,
                        attachment_id=identity,
                        received_at=received,
                        imported_at=datetime.now(UTC),
                        sha256=info["sha256"],
                        review_required=True,
                    )
                )
                scan.imported += 1
                scan.byte_count += len(content)
                imported, consumed = scan.imported, scan.byte_count
        with Session(engine) as db, db.begin():
            scan, _owner = live_scan(db, claim)
            scan.cursor += 1
            scan.skipped += skipped or (1 if not parts else 0)
            scan.truncated = (
                scan.truncated
                or bounded_out
                or (
                    (scan.imported >= 10 or scan.byte_count >= 40 * 1024 * 1024)
                    and scan.cursor < len(scan.message_ids)
                )
            )
            scan.state = (
                "queued"
                if scan.cursor < len(scan.message_ids)
                and scan.imported < 10
                and scan.byte_count < 40 * 1024 * 1024
                else ("partial" if scan.skipped or scan.truncated else "complete")
            )
            scan.failure_code = "unsupported_or_bounded" if scan.skipped or scan.truncated else None
            scan.lease_token = scan.lease_until = None
            scan.attempts = 0
    except ApiProblem as failure:
        finish_scan_failure(engine, claim, GmailFailure(failure.code))
    except GmailFailure as failure:
        finish_scan_failure(engine, claim, failure)
    except Exception:
        # Never emit exception/provider/DB text. Recovery remains bounded.
        finish_scan_failure(engine, claim, GmailFailure("processing_failed", True))
    return True


def finish_scan_failure(engine, claim, failure):
    with Session(engine) as db, db.begin():
        owner = db.scalar(
            select(DemoSession).where(DemoSession.id == claim.session_id).with_for_update()
        )
        item = db.get(GmailConnection, claim.session_id)
        scan = db.scalar(select(GmailScan).where(GmailScan.id == claim.id).with_for_update())
        if scan.state != "processing" or scan.lease_token != claim.lease_token:
            return
        if (
            failure.code in {"revoked", "key_unavailable", "refresh_missing"}
            and item
            and item.version == claim.connection_version
        ):
            clear_connection(item, "reconnect_required")
        if owner.expires_at <= datetime.now(UTC) or failure.code in {
            "authorization_changed",
            "stale_lease",
        }:
            scan.state = "cancelled"
        elif failure.transient and scan.attempts < 3 and scan.expires_at > datetime.now(UTC):
            scan.state = "queued"
            scan.available_at = datetime.now(UTC) + timedelta(seconds=2**scan.attempts)
        else:
            scan.state = "partial" if scan.imported else "failed"
        scan.failure_code = failure.code
        scan.lease_token = scan.lease_until = None
