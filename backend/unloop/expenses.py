"""Owner-private revisioned Meal workspace; models provide suggestions, code owns writes."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from unloop.api import ApiProblem, Db, MutationOwner, Owner
from unloop.contracts import StrictModel
from unloop.evidence import own_report
from unloop.fx import currency
from unloop.models import (
    Document,
    EvidenceLink,
    Expense,
    ExpenseJob,
    ExpenseRevision,
    ExtractionSuggestion,
)

router = APIRouter(prefix="/api")
REQUIRED = [
    "category",
    "merchant",
    "receiptDate",
    "originalAmount",
    "transactionCurrency",
    "mealType",
]
FIELDS = [*REQUIRED, "vatAmount"]
FINANCIAL = {"category", "receiptDate", "originalAmount", "transactionCurrency", "mealType"}


class SelectedReceipt(StrictModel):
    documentId: UUID = Field(strict=False)


class ExpenseCommand(StrictModel):
    version: int = Field(ge=1)
    facts: dict[str, str | None] = Field(default_factory=dict)
    confirmed: bool = False
    excluded: bool = False

    @model_validator(mode="after")
    def validate_facts(self):
        check_facts(self.facts)
        return self


class VersionCommand(StrictModel):
    version: int = Field(ge=1)


def check_facts(facts):
    if set(facts) - set(FIELDS):
        raise ValueError("Unknown expense field")
    for key, value in facts.items():
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip() or len(value) > 200:
            raise ValueError("Expense fields must contain bounded text")
        if key == "category" and value not in {"meals", "air", "groundTransport"}:
            raise ValueError("Unsupported category")
        if key == "mealType" and value not in {"breakfast", "lunch", "dinner"}:
            raise ValueError("Choose Breakfast, Lunch or Dinner")
        if key == "receiptDate":
            parsed = date.fromisoformat(value)
            if (
                parsed.isoformat() != value
                or not date(2000, 1, 1) <= parsed <= datetime.now(UTC).date()
            ):
                raise ValueError("Receipt date must be an exact past/current calendar date")
        if key in {"originalAmount", "vatAmount"}:
            if not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,6})?", value):
                raise ValueError("Amount must be a bounded decimal string")
            if Decimal(value) <= 0 and key == "originalAmount":
                raise ValueError("Receipt total must be positive")
        if key == "transactionCurrency":
            currency(value)
    if facts.get("vatAmount") is not None and facts.get("originalAmount") is not None:
        if Decimal(facts["vatAmount"]) > Decimal(facts["originalAmount"]):
            raise ValueError("VAT cannot exceed the full receipt total")


def own_expense(db, owner, id, *, lock=False):
    query = select(Expense).where(Expense.id == id, Expense.session_id == owner.id)
    item = db.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise ApiProblem(404, "not_found", "Expense not found.")
    own_report(db, owner, item.report_id)
    return item


def snapshot(db, item):
    db.add(
        ExpenseRevision(
            id=item.revision_id,
            session_id=item.session_id,
            expense_id=item.id,
            version=item.version,
            snapshot={
                "facts": item.facts,
                "locks": item.locks,
                "provenance": item.provenance,
                "confirmed": item.confirmed,
                "issues": item.issues,
                "calculation": item.calculation,
            },
            created_at=datetime.now(UTC),
        )
    )
    db.flush()


def revise(db, item):
    item.version += 1
    item.revision_id = uuid4()
    snapshot(db, item)


def enqueue(db, item, kind):
    db.add(
        ExpenseJob(
            session_id=item.session_id,
            expense_id=item.id,
            revision_id=item.revision_id,
            kind=kind,
            state="queued",
            attempts=0,
            call_count=0,
            available_at=datetime.now(UTC),
        )
    )
    item.state, item.failure_code = "queued", None


def question(item):
    if item.state == "conflict":
        return {
            "field": "mealType",
            "message": (
                "Another receipt has this date and meal type. Choose the single "
                "receipt to claim; amounts cannot be pooled."
            ),
        }
    if item.state == "unsupported":
        return {
            "field": "category",
            "message": (
                "This increment supports Meals only. Correct the category if the receipt is a Meal."
            ),
        }
    if item.state == "unreadable":
        return {
            "field": "receipt",
            "message": "The receipt could not be read. Upload a clearer original and select it.",
        }
    if item.issues:
        issue = item.issues[0]
        return {
            "field": issue["field"],
            "message": "Check the receipt: "
            + issue["reason"]
            + ". Confirm the affected fact or provide clearer single-receipt evidence.",
        }
    for field in REQUIRED:
        if not item.facts.get(field):
            return {
                "field": field,
                "message": {
                    "mealType": (
                        "Is this Breakfast, Lunch or Dinner? Check the receipt; amount "
                        "alone cannot decide."
                    ),
                    "originalAmount": (
                        "What is the complete receipt total, including listed tips/service charges?"
                    ),
                    "receiptDate": (
                        "Confirm the receipt date shown on the original, including the year."
                    ),
                }.get(field, "Check the receipt and confirm " + field + "."),
            }
    if not item.confirmed and any(key in item.locks for key in REQUIRED):
        return {
            "field": "confirmation",
            "message": (
                "Confirm the corrected facts against the receipt before calculations continue."
            ),
        }
    return None


def view(db, item):
    suggestion = db.scalar(
        select(ExtractionSuggestion)
        .join(ExpenseJob, ExtractionSuggestion.job_id == ExpenseJob.id)
        .where(ExpenseJob.expense_id == item.id)
        .order_by(ExtractionSuggestion.created_at.desc())
        .limit(1)
    )
    return {
        "id": str(item.id),
        "reportId": str(item.report_id),
        "documentId": str(item.document_id),
        "version": item.version,
        "revisionId": str(item.revision_id),
        "state": item.state,
        "facts": item.facts,
        "lockedFields": item.locks,
        "provenance": item.provenance,
        "confirmed": item.confirmed,
        "issues": item.issues,
        "calculation": item.calculation,
        "failureCode": item.failure_code,
        "question": question(item),
        "originalUrl": f"/api/documents/{item.document_id}/original",
        "suggestion": None
        if suggestion is None
        else {
            "revisionId": str(suggestion.revision_id),
            "output": suggestion.output,
            "diagnostics": suggestion.diagnostics,
        },
    }


@router.post("/reports/{report_id}/expenses", status_code=201)
def create_expense(report_id: UUID, body: SelectedReceipt, db: Db, owner: MutationOwner):
    own_report(db, owner, report_id)
    document = db.scalar(
        select(Document)
        .join(EvidenceLink, EvidenceLink.document_id == Document.id)
        .where(
            Document.id == body.documentId,
            Document.session_id == owner.id,
            EvidenceLink.report_id == report_id,
        )
    )
    if document is None:
        raise ApiProblem(404, "not_found", "Select retained evidence from this report.")
    if document.state != "validated":
        raise ApiProblem(
            409, "evidence_not_ready", "Wait for evidence validation; validation is not extraction."
        )
    existing = db.scalar(
        select(Expense).where(Expense.session_id == owner.id, Expense.document_id == document.id)
    )
    if existing:
        return {"expense": view(db, existing), "reused": True}
    item = Expense(
        id=uuid4(),
        session_id=owner.id,
        report_id=report_id,
        document_id=document.id,
        version=1,
        revision_id=uuid4(),
        state="queued",
        facts={},
        locks=[],
        provenance={},
        confirmed=False,
        created_at=datetime.now(UTC),
    )
    db.add(item)
    db.flush()
    snapshot(db, item)
    enqueue(db, item, "extract")
    return {"expense": view(db, item), "reused": False}


@router.get("/reports/{report_id}/expenses")
def list_expenses(report_id: UUID, db: Db, owner: Owner):
    own_report(db, owner, report_id)
    rows = db.scalars(
        select(Expense)
        .where(Expense.session_id == owner.id, Expense.report_id == report_id)
        .order_by(Expense.created_at)
    ).all()
    total = sum(
        (
            Decimal(row.calculation["claimGbp"])
            for row in rows
            if row.state == "review" and row.calculation
        ),
        Decimal("0.00"),
    )
    return {
        "expenses": [view(db, row) for row in rows],
        "preparedClaimGbp": str(total),
        "label": "Prepared draft total; not submitted or approved",
    }


@router.get("/expenses/{id}")
def read_expense(id: UUID, db: Db, owner: Owner):
    return view(db, own_expense(db, owner, id))


@router.patch("/expenses/{id}")
def edit_expense(id: UUID, body: ExpenseCommand, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    if body.version != item.version:
        raise ApiProblem(409, "stale_revision", "This expense changed. Reload before correcting.")
    facts = {**item.facts, **body.facts}
    try:
        check_facts(facts)
    except ValueError:
        raise ApiProblem(
            422, "invalid_facts", "Review receipt date, amount, currency and VAT."
        ) from None
    changed = {key for key in body.facts if facts.get(key) != item.facts.get(key)}
    if (
        not changed
        and set(body.facts).issubset(item.locks)
        and body.confirmed == item.confirmed
        and (item.state == "excluded") == body.excluded
    ):
        return view(db, item)
    previous = item.calculation
    item.facts = facts
    item.locks = sorted(set(item.locks) | set(body.facts))
    item.provenance = {
        **item.provenance,
        **{
            key: {
                "source": "human",
                "documentId": str(item.document_id),
                "confirmed": body.confirmed,
            }
            for key in body.facts
        },
    }
    item.confirmed = body.confirmed
    if body.confirmed:
        item.issues = [
            issue
            for issue in item.issues
            if issue["reason"] in {"multipleReceipts", "unreadable"}
            or issue["field"] not in body.facts
        ]
    if changed & FINANCIAL or body.excluded or not body.confirmed:
        item.calculation = None
    revise(db, item)
    if body.excluded:
        item.state = "excluded"
    elif previous and not changed & FINANCIAL and body.confirmed:
        item.state = "review"
    else:
        enqueue(db, item, "calculate")
    return view(db, item)


@router.post("/expenses/{id}/recheck")
def recheck_expense(id: UUID, body: VersionCommand, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    if body.version != item.version:
        raise ApiProblem(409, "stale_revision", "Reload the saved expense first.")
    revise(db, item)
    enqueue(db, item, "calculate")
    return view(db, item)


@router.post("/expenses/{id}/extract")
def rerun_expense(id: UUID, body: VersionCommand, request: Request, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    if body.version != item.version:
        raise ApiProblem(409, "stale_revision", "Reload the saved expense first.")
    if request.app.state.a1_settings is None:
        raise ApiProblem(
            503,
            "model_unconfigured",
            "Paid extraction is disabled until private key and reviewed budgets are configured.",
        )
    revise(db, item)
    enqueue(db, item, "extract")
    return view(db, item)


@router.post("/expenses/{id}/choose")
def choose_conflicting_receipt(id: UUID, body: VersionCommand, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    if body.version != item.version or not all(
        item.facts.get(key) for key in ["receiptDate", "mealType"]
    ):
        raise ApiProblem(
            409, "stale_revision", "Reload and complete the receipt date and meal type."
        )
    others = db.scalars(
        select(Expense).where(
            Expense.session_id == owner.id, Expense.id != item.id, Expense.state != "excluded"
        )
    ).all()
    for other in others:
        if (
            all(other.facts.get(key) == item.facts[key] for key in ["receiptDate", "mealType"])
            and other.facts.get("category") == "meals"
        ):
            other.calculation, other.state = None, "excluded"
            revise(db, other)
    revise(db, item)
    enqueue(db, item, "calculate")
    return view(db, item)
