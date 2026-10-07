"""Authorized Phase 1A commands. Objects belong to a server-owned session."""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from unloop.intake import ConfirmationInput, EmptyInput, PersonaInput, ProposalInput, parse_report
from unloop.models import DemoProfile, DemoSession, Report

router = APIRouter(prefix="/api")
PROPOSAL_TTL_SECONDS = 20 * 60


class ApiProblem(Exception):
    def __init__(self, status: int, code: str, message: str, *, clear_cookie=False):
        self.status, self.code, self.message = status, code, message
        self.clear_cookie = clear_cookie


def database(request: Request):
    if request.app.state.engine is None:
        raise ApiProblem(503, "database_unavailable", "Report storage is not configured.")
    # Function scope commits before sending a successful response/cookie.
    with Session(request.app.state.engine, expire_on_commit=False) as db, db.begin():
        yield db


Db = Annotated[Session, Depends(database, scope="function")]


def resolve_session(request: Request, db: Session, *, lock: bool) -> DemoSession:
    cookie = request.cookies.get(request.app.state.settings.cookie_name)
    if not cookie:
        raise ApiProblem(401, "session_required", "Start a demo session to continue.")
    if len(cookie) != 43:
        raise ApiProblem(401, "invalid_session", "This demo session is invalid.", clear_cookie=True)
    token_hash = hashlib.sha256(cookie.encode()).hexdigest()
    # Serialize persona switching and authorized actions/concurrent confirmations.
    query = select(DemoSession).where(DemoSession.token_hash == token_hash)
    owner = db.scalar(query.with_for_update() if lock else query)
    if owner is None:
        raise ApiProblem(401, "invalid_session", "This demo session is invalid.", clear_cookie=True)
    if owner.expires_at <= datetime.now(UTC):
        raise ApiProblem(
            401, "session_expired", "Your demo session expired. Start a new one.", clear_cookie=True
        )
    return owner


def current_session(request: Request, db: Db) -> DemoSession:
    return resolve_session(request, db, lock=True)


Owner = Annotated[DemoSession, Depends(current_session)]


def mutation_session(request: Request, owner: Owner) -> DemoSession:
    if not secrets.compare_digest(
        request.headers.get("x-csrf-token", "").encode(), owner.csrf_token.encode()
    ):
        raise ApiProblem(403, "csrf_failed", "Refresh this app before making changes.")
    return owner


MutationOwner = Annotated[DemoSession, Depends(mutation_session)]


def employee(owner: DemoSession):
    if owner.active_persona != "employee":
        raise ApiProblem(403, "employee_required", "Switch to Employee to access draft reports.")


def session_view(db: Session, owner: DemoSession):
    profile = db.scalar(
        select(DemoProfile).where(
            DemoProfile.session_id == owner.id, DemoProfile.persona == owner.active_persona
        )
    )
    return {
        "persona": owner.active_persona,
        "profile": {
            "id": str(profile.id),
            "displayName": profile.display_name,
            **({"grade": profile.grade} if owner.active_persona == "employee" else {}),
        },
        "csrfToken": owner.csrf_token,
        "expiresAt": owner.expires_at.isoformat(),
    }


def report_view(report: Report):
    return {
        "id": str(report.id),
        "name": report.name,
        "startDate": report.start_date.isoformat(),
        "endDate": report.end_date.isoformat(),
        "businessPurpose": report.business_purpose,
        "status": report.status,
        "version": report.version,
        "currency": "GBP",
        "createdAt": report.created_at.isoformat(),
    }


def proposal_signer(owner: DemoSession):
    return URLSafeTimedSerializer(
        owner.proposal_secret,
        salt="unloop-report-proposal-v1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


@router.get("/health")
def health():
    return {"service": "unloop", "status": "ok"}


@router.get("/readiness")
def readiness(db: Db):
    version = db.scalar(text("SELECT version_num FROM alembic_version"))
    if version != "0005_phase2_meals":
        raise ApiProblem(503, "migration_required", "Apply the database migrations.")
    db.execute(select(DemoSession.id).limit(1))
    return {"service": "unloop", "database": "ready", "schemaVersion": version}


@router.get("/session")
def read_session(db: Db, owner: Owner):
    return session_view(db, owner)


@router.post("/session", status_code=201)
def start_session(_body: EmptyInput, request: Request, response: Response, db: Db):
    if request.cookies.get(request.app.state.settings.cookie_name):
        owner = current_session(request, db)
        response.status_code = 200
        return session_view(db, owner)
    db.execute(text("SELECT pg_advisory_xact_lock(781033)"))
    if db.scalar(select(func.count()).select_from(DemoSession)) >= 1000:
        raise ApiProblem(
            503, "demo_capacity", "Demo session capacity reached; owner cleanup is required."
        )
    settings = request.app.state.settings
    raw_token, now = secrets.token_urlsafe(32), datetime.now(UTC)
    owner = DemoSession(
        id=uuid4(),
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        csrf_token=secrets.token_urlsafe(32),
        proposal_secret=secrets.token_urlsafe(32),
        active_persona="employee",
        created_at=now,
        expires_at=now + timedelta(seconds=settings.session_ttl_seconds),
    )
    db.add(owner)
    db.flush()
    db.add_all(
        [
            DemoProfile(
                session_id=owner.id, persona="employee", display_name="Demo employee", grade="C"
            ),
            DemoProfile(
                session_id=owner.id, persona="manager", display_name="Demo manager", grade=None
            ),
        ]
    )
    db.flush()
    response.set_cookie(
        settings.cookie_name,
        raw_token,
        max_age=settings.session_ttl_seconds,
        expires=owner.expires_at,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
    return session_view(db, owner)


@router.patch("/session/persona")
def switch_persona(body: PersonaInput, db: Db, owner: MutationOwner):
    owner.active_persona = body.persona
    return session_view(db, owner)


@router.post("/report-proposals")
def propose_report(body: ProposalInput, owner: MutationOwner):
    employee(owner)
    parsed = parse_report(body.message)
    parsed["proposalToken"] = proposal_signer(owner).dumps(
        {"owner": str(owner.id), "confirmationId": str(uuid4())}
    )
    parsed["message"] = (
        "Review these details. Your report will be saved only when you confirm."
        if parsed["ready"]
        else " ".join(parsed["questions"])
    )
    return parsed


@router.post("/reports", status_code=201)
def confirm_report(body: ConfirmationInput, response: Response, db: Db, owner: MutationOwner):
    employee(owner)
    try:
        proposal = proposal_signer(owner).loads(body.proposalToken, max_age=PROPOSAL_TTL_SECONDS)
        if proposal["owner"] != str(owner.id):
            raise BadSignature("Owner mismatch")
        confirmation_id = UUID(proposal["confirmationId"])
    except SignatureExpired as exc:
        raise ApiProblem(
            409, "proposal_expired", "Describe the report again to refresh its proposal."
        ) from exc
    except (BadSignature, ValueError, KeyError, TypeError) as exc:
        raise ApiProblem(
            400, "invalid_proposal", "Describe the report again before confirming."
        ) from exc
    header = body.header
    existing = db.scalar(
        select(Report).where(
            Report.session_id == owner.id, Report.confirmation_id == confirmation_id
        )
    )
    if existing:
        if (existing.name, existing.start_date, existing.end_date, existing.business_purpose) != (
            header.name,
            header.startDate,
            header.endDate,
            header.businessPurpose,
        ):
            raise ApiProblem(
                409,
                "confirmation_conflict",
                "This proposal was already saved with different details.",
            )
        response.status_code = 200
        return report_view(existing)
    profile = db.scalar(
        select(DemoProfile).where(
            DemoProfile.session_id == owner.id, DemoProfile.persona == "employee"
        )
    )
    if (
        db.scalar(select(func.count()).select_from(Report).where(Report.session_id == owner.id))
        >= 50
    ):
        raise ApiProblem(409, "report_limit", "This demo session supports up to 50 reports.")
    report = Report(
        session_id=owner.id,
        employee_profile_id=profile.id,
        confirmation_id=confirmation_id,
        name=header.name,
        start_date=header.startDate,
        end_date=header.endDate,
        business_purpose=header.businessPurpose,
        created_at=datetime.now(UTC),
    )
    db.add(report)
    db.flush()
    return report_view(report)


@router.get("/reports")
def list_reports(db: Db, owner: Owner):
    if owner.active_persona == "manager":
        return {"reports": []}
    reports = db.scalars(
        select(Report)
        .where(Report.session_id == owner.id)
        .order_by(Report.created_at.desc(), Report.id)
    ).all()
    return {"reports": [report_view(report) for report in reports]}


@router.get("/reports/{report_id}")
def read_report(report_id: UUID, db: Db, owner: Owner):
    employee(owner)
    report = db.scalar(select(Report).where(Report.id == report_id, Report.session_id == owner.id))
    if report is None:
        raise ApiProblem(404, "report_not_found", "This report is not available in your session.")
    return report_view(report)
