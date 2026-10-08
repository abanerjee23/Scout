"""Code-owned submitted snapshots and partial releases; persona never grants downstream access."""

import hashlib
import json
import secrets
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Query, Request, Response
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import Field
from sqlalchemy import func, select

from unloop.api import ApiProblem, Db, MutationOwner, Owner, employee, report_view
from unloop.contracts import StrictModel
from unloop.evidence import own_report
from unloop.expenses import meal_slot, ready_facts, refresh_conflicts
from unloop.models import (
    ApprovalRelease,
    ApprovedLine,
    ApprovedMealSlot,
    Document,
    DocumentBytes,
    Expense,
    InboxEvent,
    MealPolicyVersion,
    ProcessingReady,
    Report,
    ReviewQuestion,
    Submission,
    SubmittedLine,
)
from unloop.policy_registry import registry

router = APIRouter(prefix="/api")
Id = Annotated[UUID, Field(strict=False)]


def manager(owner):
    if owner.active_persona != "manager":
        raise ApiProblem(
            403, "manager_required", "Switch to Manager to review submitted snapshots."
        )


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def signer(owner, purpose):
    return URLSafeTimedSerializer(
        owner.proposal_secret,
        salt="unloop-" + purpose + "-1",
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def verify(owner, purpose, token):
    try:
        return signer(owner, purpose).loads(token, max_age=600)
    except (BadSignature, SignatureExpired):
        raise ApiProblem(
            409, "preview_expired", "Refresh the exact line/amount preview before confirming."
        ) from None


def event(db, owner, report_id, persona, key, payload):
    db.add(
        InboxEvent(
            session_id=owner.id,
            report_id=report_id,
            persona=persona,
            event_key=key,
            payload=payload,
            read=False,
            created_at=datetime.now(UTC),
        )
    )


def expenses(db, owner, report_id):
    return db.scalars(
        select(Expense)
        .where(Expense.session_id == owner.id, Expense.report_id == report_id)
        .order_by(Expense.created_at, Expense.id)
    ).all()


def eligible(db, item, policy):
    if item.state != "review" or not ready_facts(db, item) or not item.calculation:
        return False
    calc = item.calculation
    if (
        policy is None
        or calc.get("policyVersion") != policy.version
        or calc.get("expenseRevisionId") != str(item.revision_id)
        or calc.get("eligible", True) is not True
    ):
        return False
    if not Decimal(calc["claimGbp"]).is_finite() or Decimal(calc["claimGbp"]) <= 0:
        return False
    snapshot = db.get(MealPolicyVersion, policy.version)
    if (
        snapshot is None
        or snapshot.facts.get("source", {}).get("sourceHash") != registry(policy)["sourceHash"]
    ):
        return False
    if db.scalar(select(ApprovedLine.id).where(ApprovedLine.expense_id == item.id)):
        return False
    slot = meal_slot(item)
    if slot and db.get(ApprovedMealSlot, (item.session_id, date.fromisoformat(slot[0]), slot[1])):
        return False
    return True


def preview_data(db, owner, report, policy):
    rows = expenses(db, owner, report.id)
    refresh_conflicts(db, owner.id, [meal_slot(row) for row in rows])
    valid = [row for row in rows if eligible(db, row, policy)]
    data = [
        {
            "expenseId": str(row.id),
            "revisionId": str(row.revision_id),
            "version": row.version,
            "merchant": row.facts["merchant"],
            "claimGbp": row.calculation["claimGbp"],
            "policyVersion": row.calculation["policyVersion"],
        }
        for row in valid
    ]
    blocked = [
        {
            "expenseId": str(row.id),
            "state": row.state,
            "reason": "Recheck facts, evidence and the active policy before submission.",
        }
        for row in rows
        if row not in valid and row.state not in {"excluded", "approved"}
    ]
    return {
        "reportId": str(report.id),
        "reportVersion": report.version,
        "eligibleLines": data,
        "blockedLines": blocked,
        "eligibleClaimGbp": str(sum((Decimal(row["claimGbp"]) for row in data), Decimal("0.00"))),
        "excludedCount": sum(row.state == "excluded" for row in rows),
        "choices": ["Submit selected eligible lines", "Wait and resolve remaining lines"],
    }


@router.post("/reports/{report_id}/submission-preview")
def submission_preview(report_id: UUID, request: Request, db: Db, owner: MutationOwner):
    report = own_report(db, owner, report_id)
    value = preview_data(db, owner, report, request.app.state.meal_policy)
    return {**value, "previewToken": signer(owner, "submit").dumps(value)}


class SubmitInput(StrictModel):
    requestId: Id
    previewToken: str = Field(min_length=1, max_length=16000)
    expenseIds: list[Id] = Field(min_length=1, max_length=50)
    confirmed: Literal[True]


def submission_view(db, value):
    lines = db.scalars(
        select(SubmittedLine)
        .where(SubmittedLine.submission_id == value.id)
        .order_by(SubmittedLine.id)
    ).all()
    return {
        "id": str(value.id),
        "reportId": str(value.report_id),
        "version": value.version,
        "header": value.header,
        "claimGbp": value.total_gbp,
        "lines": [
            {
                "id": str(line.id),
                "expenseId": str(line.expense_id),
                "revisionId": str(line.revision_id),
                "state": line.state,
                "version": line.version,
                "snapshot": line.snapshot,
            }
            for line in lines
        ],
    }


@router.post("/reports/{report_id}/submissions", status_code=201)
def submit(report_id: UUID, body: SubmitInput, request: Request, db: Db, owner: MutationOwner):
    report = own_report(db, owner, report_id)
    digest = fingerprint({"reportId": str(report_id), **body.model_dump(mode="json")})
    old = db.scalar(
        select(Submission).where(
            Submission.session_id == owner.id, Submission.request_id == body.requestId
        )
    )
    if old:
        if old.request_hash != digest:
            raise ApiProblem(
                409, "request_conflict", "This request already submitted a different preview."
            )
        return submission_view(db, old)
    proposed = verify(owner, "submit", body.previewToken)
    current = preview_data(db, owner, report, request.app.state.meal_policy)
    if proposed != current:
        raise ApiProblem(
            409, "stale_preview", "The report changed. Refresh the submission preview."
        )
    ids = set(body.expenseIds)
    if len(ids) != len(body.expenseIds) or not ids <= {
        UUID(row["expenseId"]) for row in current["eligibleLines"]
    }:
        raise ApiProblem(
            409, "ineligible_lines", "Choose only eligible lines from this exact preview."
        )
    rows = [row for row in expenses(db, owner, report_id) if row.id in ids]
    report.version += 1
    total = str(sum((Decimal(row.calculation["claimGbp"]) for row in rows), Decimal("0.00")))
    report.status = (
        "partially_approved"
        if db.scalar(
            select(ApprovalRelease.id).where(ApprovalRelease.report_id == report_id).limit(1)
        )
        else "submitted"
    )
    submission = Submission(
        session_id=owner.id,
        report_id=report_id,
        request_id=body.requestId,
        request_hash=digest,
        version=report.version,
        header=report_view(report),
        total_gbp=total,
        created_at=datetime.now(UTC),
    )
    db.add(submission)
    db.flush()
    for item in rows:
        previous = db.scalars(
            select(SubmittedLine).where(
                SubmittedLine.session_id == owner.id,
                SubmittedLine.expense_id == item.id,
                SubmittedLine.state.in_(["pending", "held", "returned"]),
            )
        ).all()
        for line in previous:
            line.state, line.version = "superseded", line.version + 1
        db.add(
            SubmittedLine(
                session_id=owner.id,
                submission_id=submission.id,
                expense_id=item.id,
                revision_id=item.revision_id,
                snapshot={
                    "facts": item.facts,
                    "calculation": item.calculation,
                    "receiptDocumentId": str(item.document_id),
                    "supportingDocumentIds": item.provenance.get("supportingDocumentIds", []),
                    "policySourceHash": registry(request.app.state.meal_policy)["sourceHash"],
                },
                state="pending",
                version=1,
            )
        )
    for persona, kind in [("employee", "submission_confirmed"), ("manager", "review_requested")]:
        event(
            db,
            owner,
            report_id,
            persona,
            f"{kind}:{submission.id}",
            {
                "type": kind,
                "submissionId": str(submission.id),
                "version": submission.version,
                "expenseIds": [str(row.id) for row in rows],
                "claimGbp": total,
            },
        )
    db.flush()
    return submission_view(db, submission)


@router.get("/reports/{report_id}/submissions")
def employee_submissions(report_id: UUID, db: Db, owner: Owner):
    own_report(db, owner, report_id)
    rows = db.scalars(
        select(Submission)
        .where(Submission.session_id == owner.id, Submission.report_id == report_id)
        .order_by(Submission.version)
    ).all()
    releases = db.scalars(
        select(ApprovalRelease).where(
            ApprovalRelease.session_id == owner.id, ApprovalRelease.report_id == report_id
        )
    ).all()
    pending = db.scalars(
        select(SubmittedLine)
        .join(Submission, Submission.id == SubmittedLine.submission_id)
        .where(
            Submission.session_id == owner.id,
            Submission.report_id == report_id,
            SubmittedLine.state.in_(["pending", "held", "returned"]),
        )
    ).all()
    return {
        "submissions": [submission_view(db, value) for value in rows],
        "approvedClaimGbp": str(
            sum((Decimal(value.total_gbp) for value in releases), Decimal("0.00"))
        ),
        "pendingSubmittedClaimGbp": str(
            sum(
                (Decimal(value.snapshot["calculation"]["claimGbp"]) for value in pending),
                Decimal("0.00"),
            )
        ),
    }


def own_line(db, owner, id):
    line = db.scalar(
        select(SubmittedLine).where(SubmittedLine.id == id, SubmittedLine.session_id == owner.id)
    )
    if line is None:
        raise ApiProblem(404, "not_found", "Submitted line not found.")
    return line


def questions_for(db, line):
    rows = db.scalars(
        select(ReviewQuestion)
        .where(ReviewQuestion.line_id == line.id)
        .order_by(ReviewQuestion.created_at)
    ).all()
    return [
        {
            "id": str(value.id),
            "question": value.question,
            "response": value.response,
            "version": value.version,
        }
        for value in rows
    ]


def active_line(db, line):
    item = db.get(Expense, line.expense_id)
    return (
        line.state in {"pending", "held"}
        and item.revision_id == line.revision_id
        and item.state == "review"
    )


@router.get("/review/reports")
def manager_reports(db: Db, owner: Owner):
    manager(owner)
    rows = db.scalars(
        select(Submission)
        .where(Submission.session_id == owner.id)
        .order_by(Submission.created_at, Submission.id)
    ).all()
    groups = {}
    for submission in rows:
        group = groups.setdefault(
            str(submission.report_id),
            {
                "reportId": str(submission.report_id),
                "header": submission.header,
                "submissions": [],
                "approvedClaimGbp": "0.00",
                "pendingSubmittedClaimGbp": "0.00",
            },
        )
        value = submission_view(db, submission)
        for line in value["lines"]:
            record = db.get(SubmittedLine, UUID(line["id"]))
            line["needsResubmission"] = (
                record.state in {"pending", "held", "returned"}
                and db.get(Expense, record.expense_id).revision_id != record.revision_id
            )
            line["questions"] = questions_for(db, record)
            line["receiptUrl"] = f"/api/review/lines/{record.id}/receipt"
            if record.state in {"pending", "held", "returned"}:
                group["pendingSubmittedClaimGbp"] = str(
                    Decimal(group["pendingSubmittedClaimGbp"])
                    + Decimal(record.snapshot["calculation"]["claimGbp"])
                )
        group["submissions"].append(value)
    for group in groups.values():
        releases = db.scalars(
            select(ApprovalRelease).where(
                ApprovalRelease.report_id == UUID(group["reportId"]),
                ApprovalRelease.session_id == owner.id,
            )
        ).all()
        group["approvedClaimGbp"] = str(
            sum((Decimal(value.total_gbp) for value in releases), Decimal("0.00"))
        )
        group["releases"] = [value.snapshot for value in releases]
    return {"reports": list(groups.values())}


@router.get("/review/lines/{id}/receipt")
def submitted_receipt(id: UUID, db: Db, owner: Owner, documentId: UUID | None = None):
    manager(owner)
    line = own_line(db, owner, id)
    ids = [line.snapshot["receiptDocumentId"], *line.snapshot.get("supportingDocumentIds", [])]
    selected = str(documentId) if documentId else ids[0]
    if selected not in ids:
        raise ApiProblem(404, "not_found", "Submitted evidence not found.")
    document = db.get(Document, UUID(selected))
    if document is None or document.session_id != owner.id:
        raise ApiProblem(404, "not_found", "Submitted evidence not found.")
    content = db.get(DocumentBytes, document.id).content
    return Response(
        content=content,
        media_type=document.mime_type,
        headers={
            "Content-Disposition": 'attachment; filename="submitted-receipt"',
            "X-Content-Type-Options": "nosniff",
        },
    )


class ReviewAction(StrictModel):
    requestId: Id
    version: int = Field(ge=1)
    action: Literal["hold", "return", "question"]
    message: str = Field(min_length=3, max_length=1000)


@router.post("/review/lines/{id}/decisions")
def decide(id: UUID, body: ReviewAction, db: Db, owner: MutationOwner):
    manager(owner)
    line = own_line(db, owner, id)
    old = db.scalar(
        select(InboxEvent).where(
            InboxEvent.session_id == owner.id,
            InboxEvent.persona == "employee",
            InboxEvent.event_key == "decision:" + str(body.requestId),
        )
    )
    signature = fingerprint({"lineId": str(id), **body.model_dump(mode="json")})
    if old:
        if old.payload.get("requestHash") != signature:
            raise ApiProblem(409, "request_conflict", "This decision request was already used.")
        return old.payload
    if line.version != body.version or line.state not in {"pending", "held", "returned"}:
        raise ApiProblem(409, "stale_line", "Reload the submitted line before deciding.")
    if body.action == "question":
        db.add(
            ReviewQuestion(
                session_id=owner.id,
                line_id=line.id,
                request_id=body.requestId,
                question=body.message.strip(),
                version=1,
                created_at=datetime.now(UTC),
            )
        )
    line.state = "returned" if body.action == "return" or line.state == "returned" else "held"
    line.version += 1
    submission = db.get(Submission, line.submission_id)
    payload = {
        "type": "line_" + body.action,
        "submissionId": str(submission.id),
        "submissionVersion": submission.version,
        "lineId": str(line.id),
        "expenseId": str(line.expense_id),
        "message": body.message.strip(),
        "requestHash": signature,
        "nextAction": "Correct and explicitly resubmit this line."
        if line.state == "returned"
        else "Respond or provide context. Other eligible lines can be released.",
    }
    event(db, owner, submission.report_id, "employee", "decision:" + str(body.requestId), payload)
    event(
        db,
        owner,
        submission.report_id,
        "manager",
        "decision:" + str(body.requestId),
        {**payload, "type": "decision_recorded"},
    )
    return payload


class ReplyInput(StrictModel):
    version: int = Field(ge=1)
    response: str = Field(min_length=1, max_length=1500)


@router.post("/review-questions/{id}/responses")
def respond(id: UUID, body: ReplyInput, db: Db, owner: MutationOwner):
    employee(owner)
    question = db.scalar(
        select(ReviewQuestion).where(ReviewQuestion.id == id, ReviewQuestion.session_id == owner.id)
    )
    if question is None:
        raise ApiProblem(404, "not_found", "Question not found.")
    line = own_line(db, owner, question.line_id)
    if question.version != body.version or line.state in {"approved", "superseded"}:
        raise ApiProblem(
            409,
            "stale_question",
            "Reload the saved discussion. Approved or superseded lines are closed.",
        )
    if not body.response.strip():
        raise ApiProblem(422, "response_required", "Enter your response.")
    question.response, question.version = body.response.strip(), question.version + 1
    submission = db.get(Submission, line.submission_id)
    event(
        db,
        owner,
        submission.report_id,
        "manager",
        f"response:{id}:{question.version}",
        {
            "type": "employee_response",
            "lineId": str(line.id),
            "expenseId": str(line.expense_id),
            "message": question.response,
            "questionId": str(id),
            "requiresResubmission": db.get(Expense, line.expense_id).revision_id
            != line.revision_id,
        },
    )
    return {"id": str(id), "version": question.version, "response": question.response}


class ReleaseSelection(StrictModel):
    lineVersions: dict[str, int] = Field(min_length=1, max_length=50)


class ReleaseInput(ReleaseSelection):
    requestId: Id
    previewToken: str = Field(min_length=1, max_length=16000)
    confirmed: Literal[True]


def release_preview_data(db, owner, body, policy):
    lines = []
    report_id = None
    for id, version in sorted(body.lineVersions.items()):
        try:
            uuid = UUID(id)
        except ValueError:
            raise ApiProblem(422, "invalid_lines", "Select saved submitted lines.") from None
        line = own_line(db, owner, uuid)
        item = db.get(Expense, line.expense_id)
        submission = db.get(Submission, line.submission_id)
        if (
            line.version != version
            or not active_line(db, line)
            or not eligible(db, item, policy)
            or line.snapshot["calculation"] != item.calculation
            or line.snapshot["facts"] != item.facts
            or line.snapshot.get("policySourceHash") != registry(policy).get("sourceHash")
        ):
            raise ApiProblem(
                409,
                "stale_or_ineligible",
                "A selected line changed, was returned, or needs rechecking/resubmission. "
                "Reload manager review.",
            )
        if report_id is not None and report_id != submission.report_id:
            raise ApiProblem(
                422, "mixed_reports", "Release selected lines from one report at a time."
            )
        report_id = submission.report_id
        lines.append(
            {
                "lineId": str(line.id),
                "expenseId": str(item.id),
                "revisionId": str(item.revision_id),
                "lineVersion": line.version,
                "claimGbp": line.snapshot["calculation"]["claimGbp"],
                "merchant": line.snapshot["facts"]["merchant"],
                "submissionId": str(submission.id),
                "submissionVersion": submission.version,
            }
        )
    return {
        "reportId": str(report_id),
        "lines": lines,
        "approvedClaimGbp": str(
            sum((Decimal(value["claimGbp"]) for value in lines), Decimal("0.00"))
        ),
        "meaning": "Processing ready after approval; payment is not performed.",
    }


@router.post("/review/release-preview")
def release_preview(body: ReleaseSelection, request: Request, db: Db, owner: MutationOwner):
    manager(owner)
    value = release_preview_data(db, owner, body, request.app.state.meal_policy)
    return {**value, "previewToken": signer(owner, "release").dumps(value)}


@router.post("/review/releases", status_code=201)
def release(body: ReleaseInput, request: Request, db: Db, owner: MutationOwner):
    manager(owner)
    digest = fingerprint(body.model_dump(mode="json"))
    old = db.scalar(
        select(ApprovalRelease).where(
            ApprovalRelease.session_id == owner.id, ApprovalRelease.request_id == body.requestId
        )
    )
    if old:
        if old.request_hash != digest:
            raise ApiProblem(
                409,
                "request_conflict",
                "This release request already approved a different preview.",
            )
        return old.snapshot
    proposed = verify(owner, "release", body.previewToken)
    current = release_preview_data(db, owner, body, request.app.state.meal_policy)
    if proposed != current:
        raise ApiProblem(409, "stale_preview", "Refresh the release preview.")
    report = db.get(Report, UUID(current["reportId"]))
    now = datetime.now(UTC)
    version = (
        db.scalar(
            select(func.count())
            .select_from(ApprovalRelease)
            .where(ApprovalRelease.report_id == report.id)
        )
        + 1
    )
    record = ApprovalRelease(
        id=uuid4(),
        session_id=owner.id,
        report_id=report.id,
        request_id=body.requestId,
        request_hash=digest,
        version=version,
        snapshot={},
        total_gbp=current["approvedClaimGbp"],
        created_at=now,
    )
    exported = []
    for value in current["lines"]:
        line = db.get(SubmittedLine, UUID(value["lineId"]))
        facts, calc = line.snapshot["facts"], line.snapshot["calculation"]
        approved = {
            "expenseId": str(line.expense_id),
            "approvedRevisionId": str(line.revision_id),
            "merchant": facts["merchant"],
            "receiptDate": facts["receiptDate"],
            "category": facts["category"],
            "originalAmount": facts["originalAmount"],
            "originalCurrency": facts["transactionCurrency"],
            "fullGbpReceiptAmount": calc["fullGbp"],
            "approvedClaimGbp": calc["claimGbp"],
        }
        exported.append(approved)
    record.snapshot = {
        "releaseId": str(record.id),
        "reportId": str(report.id),
        "releaseVersion": version,
        "approvedAt": now.isoformat(),
        "approvedTotalGbp": record.total_gbp,
        "currency": "GBP",
        "lines": exported,
        "processingStatus": "ready",
    }
    db.add(record)
    db.flush()
    slots = []
    for value, approved in zip(current["lines"], exported, strict=True):
        line = db.get(SubmittedLine, UUID(value["lineId"]))
        item = db.get(Expense, line.expense_id)
        line.state, line.version = "approved", line.version + 1
        item.state = "approved"
        db.add(
            ApprovedLine(
                session_id=owner.id,
                release_id=record.id,
                expense_id=line.expense_id,
                revision_id=line.revision_id,
                snapshot=approved,
            )
        )
        slot = meal_slot(item)
        if slot:
            db.add(
                ApprovedMealSlot(
                    session_id=owner.id,
                    receipt_date=date.fromisoformat(slot[0]),
                    meal_type=slot[1],
                    expense_id=item.id,
                )
            )
            slots.append(slot)
    db.add(ProcessingReady(release_id=record.id, state="ready", created_at=now))
    db.flush()
    refresh_conflicts(db, owner.id, slots)
    remaining = [
        item
        for item in expenses(db, owner, report.id)
        if item.state not in {"approved", "excluded"}
    ]
    report.status = "partially_approved" if remaining else "approved"
    report.version += 1
    payload = {
        "type": "approval_release",
        "releaseId": str(record.id),
        "releaseVersion": version,
        "approvedClaimGbp": record.total_gbp,
        "expenseIds": [value["expenseId"] for value in exported],
        "message": (
            "Selected submitted lines approved and processing ready. "
            "Pending lines remain open; payment has not occurred."
        ),
    }
    for persona in ["employee", "manager"]:
        event(db, owner, report.id, persona, "release:" + str(record.id), payload)
    return record.snapshot


@router.get("/inbox")
def inbox(db: Db, owner: Owner):
    rows = db.scalars(
        select(InboxEvent)
        .where(InboxEvent.session_id == owner.id, InboxEvent.persona == owner.active_persona)
        .order_by(InboxEvent.created_at.desc(), InboxEvent.id)
        .limit(200)
    ).all()
    return {
        "events": [
            {
                "id": str(value.id),
                "reportId": str(value.report_id),
                "read": value.read,
                "createdAt": value.created_at.isoformat(),
                "payload": {
                    key: item for key, item in value.payload.items() if key != "requestHash"
                },
            }
            for value in rows
        ]
    }


class ReadInput(StrictModel):
    read: bool


@router.patch("/inbox/{id}")
def read_inbox(id: UUID, body: ReadInput, db: Db, owner: MutationOwner):
    value = db.scalar(
        select(InboxEvent).where(
            InboxEvent.id == id,
            InboxEvent.session_id == owner.id,
            InboxEvent.persona == owner.active_persona,
        )
    )
    if value is None:
        raise ApiProblem(404, "not_found", "Inbox event not found.")
    value.read = body.read
    return {"id": str(id), "read": value.read}


@router.get("/reports/{report_id}/review-questions")
def employee_questions(report_id: UUID, db: Db, owner: Owner):
    own_report(db, owner, report_id)
    lines = db.scalars(
        select(SubmittedLine)
        .join(Submission, Submission.id == SubmittedLine.submission_id)
        .where(Submission.report_id == report_id, SubmittedLine.session_id == owner.id)
    ).all()
    return {
        "lines": [
            {
                "lineId": str(line.id),
                "expenseId": str(line.expense_id),
                "state": line.state,
                "questions": questions_for(db, line),
            }
            for line in lines
        ]
    }


@router.get("/approved-releases")
def approved_api(
    request: Request,
    db: Db,
    cursor: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    configured = request.app.state.approved_api_hash
    supplied = request.headers.get("authorization", "")
    if configured is None:
        raise ApiProblem(
            503, "approved_api_unconfigured", "Approved data access is not configured."
        )
    if not supplied.startswith("Bearer ") or not secrets.compare_digest(
        hashlib.sha256(supplied[7:].encode()).hexdigest(), configured
    ):
        raise ApiProblem(
            401, "downstream_credential_required", "A separate downstream credential is required."
        )
    query = select(ApprovalRelease).order_by(ApprovalRelease.created_at, ApprovalRelease.id)
    if cursor:
        prior = db.get(ApprovalRelease, cursor)
        if prior is None:
            raise ApiProblem(400, "invalid_cursor", "Use a returned release cursor.")
        from sqlalchemy import tuple_

        query = query.where(
            tuple_(ApprovalRelease.created_at, ApprovalRelease.id) > (prior.created_at, prior.id)
        )
    rows = db.scalars(query.limit(limit + 1)).all()
    return {
        "releases": [value.snapshot for value in rows[:limit]],
        "nextCursor": str(rows[limit - 1].id) if len(rows) > limit else None,
        "meaning": "Approved snapshots only. Processing ready does not mean reimbursed.",
    }
