"""Owner-private revisioned Meal workspace; models provide suggestions, code owns writes."""

import re
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from pydantic import Field, model_validator
from sqlalchemy import select

from unloop.api import ApiProblem, Db, MutationOwner, Owner
from unloop.category_fields import (
    ALL_FIELDS,
    CATEGORY_FIELDS,
    active_fields,
    cabin,
    normalize_locations,
    required,
)
from unloop.contracts import StrictModel
from unloop.evidence import own_report
from unloop.fx import currency
from unloop.models import (
    ApprovedLine,
    Document,
    EvidenceLink,
    Expense,
    ExpenseCalculation,
    ExpenseJob,
    ExpenseRevision,
    ExtractionSuggestion,
)
from unloop.policy_registry import explain

router = APIRouter(prefix="/api")
REQUIRED = [
    "category",
    "merchant",
    "receiptDate",
    "originalAmount",
    "transactionCurrency",
    "mealType",
]
FIELDS = ALL_FIELDS
FINANCIAL = set(FIELDS) - {"merchant", "vatAmount"}


class SelectedReceipt(StrictModel):
    documentId: UUID = Field(strict=False)


class ExpenseCommand(StrictModel):
    version: int = Field(ge=1)
    facts: dict[str, str | None] = Field(default_factory=dict)
    confirmed: bool = False
    excluded: bool = False
    claimLimitGbp: str | None = Field(default=None, max_length=12)

    @model_validator(mode="after")
    def validate_facts(self):
        check_facts(self.facts)
        if self.claimLimitGbp is not None and (
            not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,2})?", self.claimLimitGbp)
            or Decimal(self.claimLimitGbp) <= 0
        ):
            raise ValueError(
                "A reduced GBP claim must be a positive amount with at most two decimals"
            )
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
        if key == "journeyType" and value not in {"oneWay", "return"}:
            raise ValueError("Choose One-way or Return")
        if key == "transportType" and value not in {"taxi", "publicTransport"}:
            raise ValueError("Choose Taxi or Public transport")
        if key == "businessJourney" and value not in {"yes", "no"}:
            raise ValueError("Confirm business journey")
        if key == "cabinClass" and cabin(value) is None:
            raise ValueError("Unmapped cabin class")
        if key in {"departureDate", "returnDate"}:
            if date.fromisoformat(value).isoformat() != value:
                raise ValueError("Travel dates must use YYYY-MM-DD")
        if key == "receiptDate":
            parsed = date.fromisoformat(value)
            if (
                parsed.isoformat() != value
                or not date(2000, 1, 1) <= parsed <= datetime.now(UTC).date()
            ):
                raise ValueError("Receipt date must be an exact past/current calendar date")
        if key in {"originalAmount", "vatAmount", "penaltyAmount"}:
            if not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,6})?", value):
                raise ValueError("Amount must be a bounded decimal string")
            if Decimal(value) <= 0 and key == "originalAmount":
                raise ValueError("Receipt total must be positive")
        if key == "transactionCurrency":
            currency(value)
    if facts.get("vatAmount") is not None and facts.get("originalAmount") is not None:
        if Decimal(facts["vatAmount"]) > Decimal(facts["originalAmount"]):
            raise ValueError("VAT cannot exceed the full receipt total")

    if facts.get("category") == "air" and facts.get("journeyType") == "return":
        if (
            facts.get("returnDate")
            and facts.get("departureDate")
            and facts["returnDate"] < facts["departureDate"]
        ):
            raise ValueError("Return date cannot precede departure")
    if facts.get("penaltyAmount") and facts.get("originalAmount"):
        if Decimal(facts["penaltyAmount"]) > Decimal(facts["originalAmount"]):
            raise ValueError("Penalty cannot exceed receipt amount")


def own_expense(db, owner, id, *, lock=False):
    query = select(Expense).where(Expense.id == id, Expense.session_id == owner.id)
    item = db.scalar(query.with_for_update() if lock else query)
    if item is None:
        raise ApiProblem(404, "not_found", "Expense not found.")
    own_report(db, owner, item.report_id)
    return item


def guard_editable(db, item):
    if item.state == "approved" or db.scalar(
        select(ApprovedLine.id).where(ApprovedLine.expense_id == item.id)
    ):
        raise ApiProblem(
            409,
            "approved_immutable",
            "Approved facts and amounts are immutable. This receipt cannot be claimed again.",
        )


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
        bool(findings)
        and findings[0].get("readable") is True
        and findings[0].get("apparentRole") == "receipt"
        and sum(finding.get("apparentRole") == "receipt" for finding in findings) == 1
        and all(
            finding.get("readable") is True and finding.get("apparentRole") == "supportingDocument"
            for finding in findings[1:]
        )
        and output.get("resultState") in {"complete", "needsInformation", "unsupported"}
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
        and item.facts.get("category") in CATEGORY_FIELDS
        and all(item.facts.get(key) for key in required(item.facts))
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
            if row.state == "approved":
                continue
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
            "message": ("Choose Air, Meals or Ground Transport if supported by the receipt."),
        }
    if (
        item.state == "needs_information"
        and item.calculation
        and item.calculation.get("outcome") == "Cabin evidence required"
    ):
        return {
            "field": "cabinClass",
            "message": (
                "Attach a receipt or booking confirmation establishing the cabin, "
                "then rerun extraction. "
                "A self-declaration cannot establish cabin entitlement."
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
    for field in required(item.facts):
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
    if not item.confirmed and any(key in item.locks for key in required(item.facts)):
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
        "facts": {
            key: value for key, value in item.facts.items() if key in active_fields(item.facts)
        },
        "claimLimitGbp": item.provenance.get("claimLimitGbp"),
        "supportingDocumentIds": item.provenance.get("supportingDocumentIds", []),
        "lockedFields": item.locks,
        "provenance": item.provenance,
        "confirmed": item.confirmed,
        "issues": item.issues,
        "calculation": item.calculation if ready_facts(db, item) else None,
        "assessment": explain(item.calculation, item.facts.get("category"))
        if ready_facts(db, item)
        else None,
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
    guard_editable(db, item)
    if body.version != item.version:
        raise ApiProblem(409, "stale_revision", "This expense changed. Reload before correcting.")
    facts = normalize_locations({**item.facts, **body.facts})
    category_changed = "category" in body.facts and facts.get("category") != item.facts.get(
        "category"
    )
    if category_changed:
        facts = {key: value for key, value in facts.items() if key in active_fields(facts)}
    try:
        check_facts(facts)
    except ValueError:
        raise ApiProblem(
            422, "invalid_facts", "Review receipt date, amount, currency and VAT."
        ) from None
    claim_limit = item.provenance.get("claimLimitGbp")
    if "claimLimitGbp" in body.model_fields_set:
        claim_limit = body.claimLimitGbp
    if facts.get("category") != "meals":
        if body.claimLimitGbp is not None:
            raise ApiProblem(
                422, "meal_claim_only", "Voluntary claim reduction is supported for Meals."
            )
        claim_limit = None
    limit_changed = claim_limit != item.provenance.get("claimLimitGbp")
    changed = {key for key in body.facts if facts.get(key) != item.facts.get(key)}
    if (
        not changed
        and not limit_changed
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
    item.locks = sorted((set(item.locks) | set(body.facts)) & set(active_fields(facts)))
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
    item.provenance = {**item.provenance, "claimLimitGbp": claim_limit}
    item.confirmed = confirmed
    if category_changed:
        item.provenance = {**item.provenance, "supportingDocumentIds": [], "factEvidence": {}}
    if category_changed:
        item.issues = [
            issue
            for issue in item.issues
            if issue["field"] in {*active_fields(facts), "receipt", "documents", "classification"}
        ]
    if confirmed:
        item.issues = [
            issue
            for issue in item.issues
            if issue["reason"] in {"multipleReceipts", "unreadable"}
            or issue["field"] in {"receipt", "documents"}
            or (
                issue["field"] not in body.facts
                and not (issue["field"] == "classification" and "category" in body.facts)
            )
        ]
    if changed & FINANCIAL or limit_changed or body.excluded or not confirmed:
        item.calculation = None
    reuse = (
        previous
        and not body.excluded
        and not changed & FINANCIAL
        and not limit_changed
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
    guard_editable(db, item)
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
    guard_editable(db, item)
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
    guard_editable(db, item)
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
    if any(other.state == "approved" for other in peers):
        raise ApiProblem(
            409,
            "meal_already_approved",
            "An approved receipt already occupies this Meal slot. Exclude this new candidate.",
        )
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


class SupportingEvidence(StrictModel):
    version: int = Field(ge=1)
    documentIds: list[Annotated[UUID, Field(strict=False)]] = Field(max_length=3)


@router.put("/expenses/{id}/supporting-evidence")
def supporting_evidence(id: UUID, body: SupportingEvidence, db: Db, owner: MutationOwner):
    item = own_expense(db, owner, id, lock=True)
    guard_editable(db, item)
    if item.version != body.version:
        raise ApiProblem(409, "stale_revision", "Reload the saved expense first.")
    if item.facts.get("category") == "meals" and body.documentIds:
        raise ApiProblem(
            409, "single_receipt_required", "Meals require one final restaurant receipt."
        )
    ids = sorted({str(value) for value in body.documentIds})
    documents = (
        db.scalars(
            select(Document)
            .join(EvidenceLink, EvidenceLink.document_id == Document.id)
            .where(
                Document.session_id == owner.id,
                EvidenceLink.report_id == item.report_id,
                Document.id.in_(body.documentIds),
                Document.state == "validated",
            )
        ).all()
        if ids
        else []
    )
    if {str(value.id) for value in documents} != set(ids) or str(item.document_id) in ids:
        raise ApiProblem(404, "not_found", "Choose validated supporting evidence in this report.")
    if ids == item.provenance.get("supportingDocumentIds", []):
        return view(db, item)
    item.provenance = {**item.provenance, "supportingDocumentIds": ids}
    item.calculation = None
    revise(db, item)
    enqueue(db, item, "extract")
    return view(db, item)
