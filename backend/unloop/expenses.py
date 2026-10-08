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
    ExpenseCalculation,
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


def receipt_eligible(db, item):
    decision = item.provenance.get("receiptEligibility")
    if decision is not None:
        return decision.get("eligible") is True
    # Previously persisted suggestions remain authoritative evidence of the check,
    # rather than inferring eligibility from transient state or fact strings.
    suggestion = db.scalar(
        select(ExtractionSuggestion)
        .join(ExpenseJob, ExtractionSuggestion.job_id == ExpenseJob.id)
        .where(ExpenseJob.expense_id == item.id)
        .order_by(ExtractionSuggestion.created_at.desc())
        .limit(1)
    )
    return bool(suggestion and receipt_decision(suggestion.output)["eligible"])


def receipt_decision(output):
    findings = output.get("documentFindings", [])
    issues = output.get("issues", [])
    eligible = (
        len(findings) == 1
        and findings[0].get("readable") is True
        and findings[0].get("apparentRole") == "receipt"
        and output.get("resultState") in {"complete", "needsInformation"}
        and not any(
            issue.get("reason") in {"multipleReceipts", "unreadable"}
            or issue.get("field") in {"receipt", "documents"}
            for issue in issues
        )
    )
    return {"eligible": eligible, "source": "extraction", "jobId": output.get("jobId")}


def ready_facts(db, item):
    return (
        receipt_eligible(db, item)
        and item.facts.get("category") == "meals"
        and all(item.facts.get(key) for key in REQUIRED)
        and not item.issues
        and (not item.locks or item.confirmed)
    )


def meal_slot(item):
    return (
        (item.facts.get("receiptDate"), item.facts.get("mealType"))
        if item.facts.get("category") == "meals"
        else None
    )


def refresh_conflicts(db, owner_id, slots):
    """Owner lock held by caller. Restore saved prerequisite state, never call a provider."""
    slots = {slot for slot in slots if slot and all(slot)}
    rows = db.scalars(select(Expense).where(Expense.session_id == owner_id)).all()
    for slot in slots:
        members = [row for row in rows if meal_slot(row) == slot]
        candidates = [row for row in members if row.state != "excluded" and ready_facts(db, row)]
        for row in members:
            if row in candidates and len(candidates) > 1:
                if row.state != "conflict":
                    row.provenance = {
                        **row.provenance,
                        "conflictBasis": {
                            "state": row.state,
                            "calculation": row.calculation,
                            "revisionId": str(row.revision_id),
                        },
                    }
                row.state, row.calculation = "conflict", None
            elif row.state == "conflict":
                basis = row.provenance.get("conflictBasis", {})
                if basis.get("revisionId") == str(row.revision_id):
                    row.state, row.calculation = basis["state"], basis.get("calculation")
                else:
                    row.state, row.calculation = "needs_information", None
                row.provenance = {
                    key: value for key, value in row.provenance.items() if key != "conflictBasis"
                }


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


def revise(db, item, *, arithmetic_source=None):
    item.version += 1
    item.revision_id = uuid4()
    if arithmetic_source is not None:
        item.calculation = {
            **item.calculation,
            "expenseRevisionId": str(item.revision_id),
            "derivation": {"kind": "reused_arithmetic", "sourceRevisionId": arithmetic_source},
        }
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
        "state": "needs_information"
        if item.state == "review" and not ready_facts(db, item)
        else item.state,
        "facts": item.facts,
        "lockedFields": item.locks,
        "provenance": item.provenance,
        "confirmed": item.confirmed,
        "issues": item.issues,
        "calculation": item.calculation if ready_facts(db, item) else None,
        "failureCode": item.failure_code,
        "question": question(item)
        if receipt_eligible(db, item)
        else {
            "field": "receipt",
            "message": (
                "Receipt eligibility is unresolved. Provide clearer single-receipt evidence "
                "or retry authorized extraction; confirming facts alone cannot resolve it."
            ),
        },
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
            if row.state == "review" and row.calculation and ready_facts(db, row)
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
    previous_revision = str(item.revision_id)
    previous_slot = meal_slot(item)
    confirmed = (
        body.confirmed if "confirmed" in body.model_fields_set or body.facts else item.confirmed
    )
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
    item.confirmed = confirmed
    if confirmed:
        item.issues = [
            issue
            for issue in item.issues
            if issue["reason"] in {"multipleReceipts", "unreadable"}
            or issue["field"] in {"receipt", "documents"}
            or issue["field"] not in body.facts
        ]
    if changed & FINANCIAL or body.excluded or not confirmed:
        item.calculation = None
    reuse = (
        previous
        and not body.excluded
        and not changed & FINANCIAL
        and confirmed
        and ready_facts(db, item)
    )
    revise(db, item, arithmetic_source=previous_revision if reuse else None)
    if body.excluded:
        item.state = "excluded"
    elif reuse:
        db.add(
            ExpenseCalculation(
                revision_id=item.revision_id, result=item.calculation, created_at=datetime.now(UTC)
            )
        )
        item.state = "review"
    else:
        enqueue(db, item, "calculate")
    refresh_conflicts(db, owner.id, [previous_slot, meal_slot(item)])
    return view(db, item)


@router.post("/expenses/{id}/recheck")
def recheck_expense(id: UUID, body: VersionCommand, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    if body.version != item.version:
        raise ApiProblem(409, "stale_revision", "Reload the saved expense first.")
    if item.state == "excluded":
        raise ApiProblem(
            409, "excluded_candidate", "Restore this candidate explicitly before processing."
        )
    revise(db, item)
    enqueue(db, item, "calculate")
    refresh_conflicts(db, owner.id, [meal_slot(item)])
    return view(db, item)


@router.post("/expenses/{id}/extract")
def rerun_expense(id: UUID, body: VersionCommand, request: Request, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    if body.version != item.version:
        raise ApiProblem(409, "stale_revision", "Reload the saved expense first.")
    if item.state == "excluded":
        raise ApiProblem(
            409, "excluded_candidate", "Restore this candidate explicitly before processing."
        )
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
    if item.state != "conflict" or not ready_facts(db, item):
        raise ApiProblem(
            409, "not_selectable", "Choose a supported eligible Meal in a current conflict."
        )
    others = db.scalars(
        select(Expense).where(
            Expense.session_id == owner.id, Expense.id != item.id, Expense.state != "excluded"
        )
    ).all()
    peers = [
        other for other in others if meal_slot(other) == meal_slot(item) and ready_facts(db, other)
    ]
    if not peers:
        raise ApiProblem(409, "not_selectable", "This Meal no longer has an eligible conflict.")
    for other in peers:
        if (
            all(other.facts.get(key) == item.facts[key] for key in ["receiptDate", "mealType"])
            and other.facts.get("category") == "meals"
        ):
            other.calculation, other.state = None, "excluded"
            revise(db, other)
    revise(db, item)
    enqueue(db, item, "calculate")
    refresh_conflicts(db, owner.id, [meal_slot(item)])
    return view(db, item)
