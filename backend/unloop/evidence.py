"""Shared employee evidence ingestion and authorized original-byte access."""

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from threading import BoundedSemaphore
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException

from unloop.api import (
    ApiProblem,
    Db,
    MutationOwner,
    Owner,
    employee,
    locked_session,
    resolve_session,
    validate_csrf,
)
from unloop.evidence_validation import MAX_BYTES, MAX_FILES, InvalidDocument
from unloop.models import Document, DocumentBytes, EvidenceJob, EvidenceLink, Report

router = APIRouter(prefix="/api")
MAX_OWNER_DOCUMENTS = 100
MAX_OWNER_BYTES = 100 * 1024**2
MAX_TOTAL_DOCUMENTS = 1000
MAX_TOTAL_BYTES = 1024**3
UPLOAD_SLOTS = BoundedSemaphore(4)


def upload_capacity():
    if not UPLOAD_SLOTS.acquire(blocking=False):
        raise ApiProblem(
            503, "upload_busy", "Four uploads are already in progress. Try again shortly."
        )
    try:
        yield
    finally:
        UPLOAD_SLOTS.release()


class UploadBodyLimit:
    """Count actual ASGI bytes inside the request middleware, before multipart spooling."""

    def __init__(self, app, limit):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or not scope["path"].endswith("/evidence")
        ):
            return await self.app(scope, receive, send)
        consumed = 0

        async def bounded_receive():
            nonlocal consumed
            message = await receive()
            consumed += len(message.get("body", b""))
            if consumed > self.limit():
                scope["unloop.upload_too_large"] = True
                # Multipart's own exception closes any already-spooled temp files.
                raise MultiPartException("Upload request limit exceeded")
            return message

        await self.app(scope, bounded_receive, send)


def bounded_validation(content, mime):
    if not 0 < len(content) <= MAX_BYTES:
        raise InvalidDocument("document_size")
    if mime not in {"image/png", "image/jpeg", "application/pdf"}:
        raise InvalidDocument("document_type")
    try:
        result = subprocess.run(
            [sys.executable, "-m", "unloop.evidence_validation", mime],
            input=content,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            env={"PATH": os.environ.get("PATH", "")},
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise InvalidDocument("validation_timeout") from None
    except OSError:
        raise InvalidDocument("validation_failed") from None
    try:
        data = json.loads(result.stdout)
    except (ValueError, UnicodeError):
        raise InvalidDocument("validation_failed") from None
    if result.returncode != 0:
        code = data.get("error")
        raise InvalidDocument(
            code
            if code
            in {
                "document_size",
                "document_type",
                "document_pages",
                "encrypted_pdf",
                "invalid_document",
            }
            else "validation_failed"
        )
    return data


def safe_filename(value, mime):
    name = (value or "document").replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^a-zA-Z0-9._ -]", "_", name).strip(" .")[:100] or "document"
    # Attach the actual type, not a user-controlled executable extension.
    stem = name.rsplit(".", 1)[0] if "." in name else name
    return stem + {"image/png": ".png", "image/jpeg": ".jpg", "application/pdf": ".pdf"}[mime]


def own_report(db, owner, report_id):
    employee(owner)
    report = db.scalar(select(Report).where(Report.id == report_id, Report.session_id == owner.id))
    if report is None:
        raise ApiProblem(404, "report_not_found", "This report is not available in your session.")
    return report


def own_document(db, owner, document_id):
    employee(owner)
    document = db.scalar(
        select(Document)
        .where(Document.id == document_id, Document.session_id == owner.id)
        .with_for_update()
    )
    if document is None:
        raise ApiProblem(
            404, "document_not_found", "This evidence is not available in your session."
        )
    return document


def queue_job(db, document, now):
    db.add(
        EvidenceJob(
            session_id=document.session_id,
            document_id=document.id,
            revision=document.revision,
            state="queued",
            attempts=0,
            available_at=now,
            created_at=now,
        )
    )


def document_view(db, document, links):
    job = db.scalar(
        select(EvidenceJob).where(
            EvidenceJob.document_id == document.id, EvidenceJob.revision == document.revision
        )
    )
    return {
        "id": str(document.id),
        "filename": document.filename,
        "mimeType": document.mime_type,
        "byteSize": document.byte_size,
        "pageCount": document.page_count,
        "state": document.state,
        "revision": document.revision,
        "failureCode": document.failure_code,
        "job": {"id": str(job.id), "state": job.state, "attempts": job.attempts} if job else None,
        "sources": sorted({link.source for link in links}),
        "originalUrl": f"/api/documents/{document.id}/original",
    }


@router.get("/reports/{report_id}/evidence")
def list_evidence(report_id: UUID, db: Db, owner: Owner):
    own_report(db, owner, report_id)
    links = db.scalars(
        select(EvidenceLink)
        .where(EvidenceLink.report_id == report_id, EvidenceLink.session_id == owner.id)
        .order_by(EvidenceLink.created_at, EvidenceLink.id)
    ).all()
    ids = list(dict.fromkeys(link.document_id for link in links))
    documents = {
        d.id: d
        for d in db.scalars(
            select(Document).where(Document.id.in_(ids), Document.session_id == owner.id)
        )
    }
    return {
        "documents": [
            document_view(db, documents[id], [link for link in links if link.document_id == id])
            for id in ids
        ]
    }


@router.post(
    "/reports/{report_id}/evidence",
    status_code=201,
    dependencies=[Depends(upload_capacity, scope="function")],
)
async def upload_evidence(report_id: UUID, request: Request):
    if request.app.state.engine is None:
        raise ApiProblem(503, "database_unavailable", "Report storage is not configured.")
    # Release the initial read transaction before receiving or parsing any file bytes.
    with Session(request.app.state.engine) as initial, initial.begin():
        owner = resolve_session(request, initial, lock=False)
        validate_csrf(request, owner)
        own_report(initial, owner, report_id)
    try:
        form = await request.form(max_files=MAX_FILES, max_fields=1, max_part_size=1024)
    except HTTPException as error:
        if error.status_code == 413 or request.scope.get("unloop.upload_too_large"):
            raise ApiProblem(413, "request_too_large", "Upload batch exceeds the limit.") from None
        raise ApiProblem(
            422, "invalid_batch", "Upload one to ten JPEG, PNG or PDF files."
        ) from None
    try:
        source = form.get("source")
        files = form.getlist("files")
        if (
            source not in {"chat", "workspace"}
            or not 1 <= len(files) <= MAX_FILES
            or any(not isinstance(file, UploadFile) for file in files)
            or set(form) != {"source", "files"}
        ):
            raise ApiProblem(422, "invalid_batch", "Choose a source and one to ten files.")
        checked = []
        for file in files:
            content = await file.read(MAX_BYTES + 1)
            try:
                info = await run_in_threadpool(bounded_validation, content, file.content_type or "")
            except InvalidDocument as error:
                raise ApiProblem(
                    422,
                    error.code,
                    "File rejected. Use a valid JPEG, PNG or PDF, up to 10 MiB and ten pages.",
                ) from None
            checked.append((content, info, safe_filename(file.filename, info["mime_type"])))
        # Fresh authority and a short lock serialize dedup only after validation.
        with Session(request.app.state.engine) as db, db.begin():
            owner = locked_session(request, db)
            validate_csrf(request, owner)
            own_report(db, owner, report_id)
            return {"documents": persist_checked(db, owner, report_id, source, checked)}
    finally:
        await form.close()


@router.get("/documents/{document_id}/original")
def original(document_id: UUID, db: Db, owner: Owner):
    document = own_document(db, owner, document_id)
    content = db.get(DocumentBytes, document.id).content
    return Response(
        content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.filename}"',
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.get("/documents/{document_id}/preview")
def preview(document_id: UUID, db: Db, owner: Owner):
    document = own_document(db, owner, document_id)
    return Response(
        db.get(DocumentBytes, document.id).content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": "inline",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post("/documents/{document_id}/retry")
def retry(document_id: UUID, db: Db, owner: MutationOwner):
    document = own_document(db, owner, document_id)
    if document.state != "failed":
        raise ApiProblem(409, "retry_not_available", "Only failed evidence can be retried.")
    document.revision += 1
    document.state, document.failure_code = "queued", None
    queue_job(db, document, datetime.now(UTC))
    db.flush()
    return {"id": str(document.id), "state": document.state, "revision": document.revision}


def persist_checked(db, owner, report_id, source, checked):
    """Caller holds fresh session authority lock; no network or parsing here."""
    db.execute(text("SELECT pg_advisory_xact_lock(781032)"))
    count, size = db.execute(
        select(func.count(), func.coalesce(func.sum(Document.byte_size), 0))
    ).one()
    own_count, own_size = db.execute(
        select(func.count(), func.coalesce(func.sum(Document.byte_size), 0)).where(
            Document.session_id == owner.id
        )
    ).one()
    hashes = set(db.scalars(select(Document.sha256).where(Document.session_id == owner.id)))
    new = {
        info["sha256"]: len(content)
        for content, info, _name in checked
        if info["sha256"] not in hashes
    }
    if (
        count + len(new) > MAX_TOTAL_DOCUMENTS
        or size + sum(new.values()) > MAX_TOTAL_BYTES
        or own_count + len(new) > MAX_OWNER_DOCUMENTS
        or own_size + sum(new.values()) > MAX_OWNER_BYTES
    ):
        raise ApiProblem(
            409,
            "storage_limit",
            "Demo evidence storage limit reached. Retained evidence needs explicit owner cleanup.",
        )
    now, result = datetime.now(UTC), []
    for content, info, filename in checked:
        document = db.scalar(
            select(Document).where(
                Document.session_id == owner.id, Document.sha256 == info["sha256"]
            )
        )
        duplicate = document is not None
        if document is None:
            document = Document(
                session_id=owner.id,
                filename=filename,
                byte_size=len(content),
                created_at=now,
                state="queued",
                revision=1,
                **info,
            )
            db.add(document)
            db.flush()
            db.add(DocumentBytes(document_id=document.id, content=content))
            queue_job(db, document, now)
        link = db.scalar(
            select(EvidenceLink).where(
                EvidenceLink.report_id == report_id,
                EvidenceLink.document_id == document.id,
                EvidenceLink.source == source,
            )
        )
        if link is None:
            db.add(
                EvidenceLink(
                    session_id=owner.id,
                    report_id=report_id,
                    document_id=document.id,
                    source=source,
                    filename=filename,
                    created_at=now,
                )
            )
        db.flush()
        result.append({"id": str(document.id), "duplicate": duplicate, "state": document.state})
    return result
