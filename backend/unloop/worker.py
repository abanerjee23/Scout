"""Leased PostgreSQL evidence-validation worker. No AI or external calls."""

import argparse
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from unloop.database import Settings, postgres_engine
from unloop.evidence import bounded_validation
from unloop.evidence_validation import InvalidDocument
from unloop.models import DemoSession, Document, DocumentBytes, EvidenceJob

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
    parser.add_argument("--once", action="store_true", help="Process at most one due job")
    args = parser.parse_args()
    if args.check:
        print(
            "Evidence worker ready: PostgreSQL leases, 3 attempts, 30s lease; "
            "15s validation timeout; no AI."
        )
        return
    settings = Settings.load()
    if not settings.database_url:
        parser.exit(2, "DATABASE_URL is required for evidence jobs.\n")
    engine = postgres_engine(settings.database_url, schema=settings.database_schema)
    try:
        if args.once:
            run_once(engine)
        else:
            while True:
                if not run_once(engine):
                    time.sleep(1)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
