"""Leased PostgreSQL evidence-validation worker. No AI or external calls."""

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session

from unloop.database import Settings, postgres_engine
from unloop.evidence import bounded_validation
from unloop.evidence_validation import InvalidDocument
from unloop.expense_worker import run_expense_once
from unloop.extraction import A1Settings, AgentsExtractor
from unloop.fx import HistoricalFx
from unloop.gmail import cleanup_expired, run_scan_once
from unloop.gmail_provider import GmailSettings, GoogleAdapter
from unloop.meal_policy import MealPolicy
from unloop.models import DemoSession, Document, DocumentBytes, EvidenceJob, GmailScan
from unloop.policy_questions import run_question_once

LEASE_SECONDS = 30
MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class Claim:
    id: UUID
    document_id: UUID
    revision: int
    token: UUID


def claim_job(engine, *, now=None):
    now = now or datetime.now(UTC)
    with Session(engine) as db, db.begin():
        job = db.scalar(
            select(EvidenceJob)
            .where(
                or_(
                    and_(EvidenceJob.state == "queued", EvidenceJob.available_at <= now),
                    and_(EvidenceJob.state == "processing", EvidenceJob.lease_until <= now),
                )
            )
            .order_by(EvidenceJob.available_at, EvidenceJob.id)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        if job is None:
            return None
        # Acquire document after job: retry only locks document, never an old job.
        document = db.scalar(
            select(Document).where(Document.id == job.document_id).with_for_update()
        )
        owner = db.get(DemoSession, job.session_id)
        if document.revision != job.revision or owner.expires_at <= now:
            job.state, job.failure_code = (
                "failed",
                "stale_revision" if document.revision != job.revision else "session_expired",
            )
            job.lease_token = job.lease_until = None
            if document.revision == job.revision:
                document.state, document.failure_code = "failed", job.failure_code
            return None
        if job.attempts >= MAX_ATTEMPTS:
            job.state = document.state = "failed"
            job.failure_code = document.failure_code = "attempts_exhausted"
            job.lease_token = job.lease_until = None
            return None
        job.attempts += 1
        job.state = document.state = "processing"
        job.failure_code = document.failure_code = None
        job.lease_token, job.lease_until = uuid4(), now + timedelta(seconds=LEASE_SECONDS)
        return Claim(job.id, job.document_id, job.revision, job.lease_token)


def finish_job(engine, claim, *, failure=None, transient=False, now=None):
    now = now or datetime.now(UTC)
    with Session(engine) as db, db.begin():
        job = db.scalar(select(EvidenceJob).where(EvidenceJob.id == claim.id).with_for_update())
        if (
            job is None
            or job.state != "processing"
            or job.lease_token != claim.token
            or job.lease_until <= now
        ):
            return False
        document = db.scalar(
            select(Document).where(Document.id == job.document_id).with_for_update()
        )
        owner = db.get(DemoSession, job.session_id)
        if (
            document.revision != claim.revision
            or job.revision != claim.revision
            or owner.expires_at <= now
        ):
            job.state, job.failure_code = "failed", "stale_revision"
            if document.revision == claim.revision:
                document.state, document.failure_code = "failed", "session_expired"
        elif failure and transient and job.attempts < MAX_ATTEMPTS:
            job.state = document.state = "queued"
            job.available_at = now + timedelta(seconds=2**job.attempts)
            job.failure_code = document.failure_code = failure
        else:
            job.state = document.state = "failed" if failure else "validated"
            job.failure_code = document.failure_code = failure
        job.lease_token = job.lease_until = None
        return True


def run_once(engine):
    claim = claim_job(engine)
    if claim is None:
        return False
    failure, transient = None, False
    try:
        # No transaction/row lock is held during bounded subprocess validation.
        with Session(engine) as db:
            document = db.get(Document, claim.document_id)
            content = db.get(DocumentBytes, claim.document_id).content
            mime, expected_hash, pages = document.mime_type, document.sha256, document.page_count
        result = bounded_validation(content, mime)
        if result["sha256"] != expected_hash or result["page_count"] != pages:
            failure = "integrity_failed"
    except InvalidDocument as error:
        failure = error.code
        transient = failure in {"validation_timeout", "validation_failed"}
    except Exception:
        failure, transient = "processing_failed", True
    finish_job(engine, claim, failure=failure, transient=transient)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Read bounded queue counts; not proof a worker is running",
    )
    parser.add_argument("--once", action="store_true", help="Process at most one due job")
    parser.add_argument(
        "--queue", choices=["all", "evidence", "expenses", "gmail", "policy"], default="all"
    )
    args = parser.parse_args()
    if args.check:
        print(
            "Evidence worker ready: PostgreSQL leases, 3 attempts, 30s lease; "
            "15s validation timeout; A1 paid calls disabled unless explicitly configured."
        )
        return
    settings = Settings.load()
    if not settings.database_url:
        parser.exit(2, "DATABASE_URL is required for evidence jobs.\n")
    engine = postgres_engine(
        settings.database_url, schema=settings.database_schema, production=settings.production
    )
    gmail_settings = GmailSettings.load(os.environ, settings.app_origin)
    adapter = GoogleAdapter(gmail_settings) if gmail_settings else None

    a1_settings = A1Settings.load(os.environ)
    extractor, policy, fx = (
        AgentsExtractor(a1_settings),
        MealPolicy.load(os.environ),
        HistoricalFx(os.environ.get("OXR_APP_ID")),
    )
    scan_process = None

    def step():
        nonlocal scan_process
        cleanup_expired(engine)
        if args.queue == "gmail":
            return run_scan_once(engine, gmail_settings, adapter) if gmail_settings else False
        expense_work = (
            run_expense_once(engine, a1_settings, extractor, policy, fx)
            if args.queue in {"all", "expenses"}
            else False
        )
        policy_work = (
            run_question_once(engine, a1_settings)
            if args.queue in {"all", "policy"} and os.environ.get("POLICY_QA_ENABLED") == "true"
            else False
        )
        evidence_work = run_once(engine) if args.queue in {"all", "evidence"} else False
        scan_work = False
        if args.queue == "all" and gmail_settings:
            if args.once:
                scan_work = run_scan_once(engine, gmail_settings, adapter)
            elif scan_process is None or scan_process.poll() is not None:
                with Session(engine) as db:
                    due = db.scalar(
                        select(GmailScan.id)
                        .where(
                            or_(
                                and_(
                                    GmailScan.state == "queued",
                                    GmailScan.available_at <= datetime.now(UTC),
                                ),
                                and_(
                                    GmailScan.state == "processing",
                                    GmailScan.lease_until <= datetime.now(UTC),
                                ),
                            )
                        )
                        .limit(1)
                    )
                if due:
                    scan_process = subprocess.Popen(
                        [sys.executable, "-m", "unloop.worker", "--queue", "gmail", "--once"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    scan_work = True
        return expense_work or evidence_work or scan_work or policy_work

    try:
        if args.diagnostics:
            with Session(engine) as db:
                evidence = dict(
                    db.execute(
                        select(EvidenceJob.state, func.count()).group_by(EvidenceJob.state)
                    ).all()
                )
                scans = dict(
                    db.execute(
                        select(GmailScan.state, func.count()).group_by(GmailScan.state)
                    ).all()
                )
            print(
                {
                    "database": "checked",
                    "evidence_counts": evidence,
                    "gmail_scan_counts": scans,
                    "worker_liveness": "not_measured",
                }
            )
        elif args.once:
            step()
        else:
            while True:
                if not step():
                    time.sleep(1)
    except Exception:
        parser.exit(
            1, "Worker stopped; verify private storage/configuration. No provider details logged.\n"
        )
    finally:
        if scan_process is not None and scan_process.poll() is None:
            scan_process.terminate()
            try:
                scan_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                scan_process.kill()
                scan_process.wait(timeout=5)
        engine.dispose()


if __name__ == "__main__":
    main()
