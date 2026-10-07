"""Durable revision-safe extraction/calculation leases; external work holds no DB transaction."""

import hashlib
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from unloop.contracts import ExtractionResult, validate_context
from unloop.expenses import FIELDS, REQUIRED, check_facts
from unloop.extraction import MODEL, PROMPT_VERSION, ExtractionFailure, observe
from unloop.fx import FxPending, saved, validate_observation
from unloop.meal_policy import CAPS, CLAUSES
from unloop.models import (
    DemoSession,
    Document,
    DocumentBytes,
    Expense,
    ExpenseCalculation,
    ExpenseJob,
    ExtractionSuggestion,
    FxObservation,
    MealPolicyVersion,
    ModelBudget,
)


@dataclass(frozen=True)
class ExpenseClaim:
    id: object
    expense_id: object
    session_id: object
    revision_id: object
    token: object
    kind: str


def authority(db, claim, *, lock=False):
    query = select(DemoSession).where(DemoSession.id == claim.session_id)
    owner = db.scalar(query.with_for_update() if lock else query)
    item = db.get(Expense, claim.expense_id)
    job = db.get(ExpenseJob, claim.id)
    if (
        job is None
        or job.state != "processing"
        or job.lease_token != claim.token
        or job.lease_until <= datetime.now(UTC)
    ):
        raise ExtractionFailure("processing_failed")
    if owner is None or owner.expires_at <= datetime.now(UTC) or owner.active_persona != "employee":
        raise ExtractionFailure("processing_failed")
    if item is None or item.revision_id != claim.revision_id or item.state == "excluded":
        raise ExtractionFailure("processing_failed")
    return owner, item


def claim_expense(engine, *, now=None):
    now = now or datetime.now(UTC)
    with Session(engine) as db, db.begin():
        query = (
            select(ExpenseJob)
            .where(
                or_(
                    and_(ExpenseJob.state == "queued", ExpenseJob.available_at <= now),
                    and_(ExpenseJob.state == "processing", ExpenseJob.lease_until <= now),
                )
            )
            .order_by(ExpenseJob.available_at, ExpenseJob.id)
            .limit(1)
        )
        candidate = db.scalar(query)
        if candidate is None:
            return None
        owner = db.scalar(
            select(DemoSession).where(DemoSession.id == candidate.session_id).with_for_update()
        )
        job = db.scalar(
            select(ExpenseJob)
            .where(ExpenseJob.id == candidate.id)
            .execution_options(populate_existing=True)
            .with_for_update(skip_locked=True)
        )
        if job is None or not (
            job.state == "queued"
            and job.available_at <= now
            or job.state == "processing"
            and job.lease_until <= now
        ):
            return None
        item = db.get(Expense, job.expense_id)
        if (
            owner.expires_at <= now
            or owner.active_persona != "employee"
            or item.revision_id != job.revision_id
            or item.state == "excluded"
            or job.attempts >= 3
        ):
            job.state, job.failure_code = (
                "failed",
                "stale_or_expired" if job.attempts < 3 else "attempts_exhausted",
            )
            job.lease_token = job.lease_until = None
            if item.revision_id == job.revision_id and item.state != "excluded":
                item.state, item.failure_code = "failed", job.failure_code
            return None
        job.attempts += 1
        job.state = item.state = "processing"
        job.lease_token, job.lease_until = uuid4(), now + timedelta(seconds=90)
        return ExpenseClaim(job.id, item.id, owner.id, job.revision_id, job.lease_token, job.kind)


def reserve_call(engine, claim, settings):
    if settings is None:
        raise ExtractionFailure("model_unconfigured")
    with Session(engine) as db, db.begin():
        authority(db, claim, lock=True)
        job = db.get(ExpenseJob, claim.id)
        if job.lease_token != claim.token or job.lease_until <= datetime.now(UTC):
            raise ExtractionFailure("processing_failed")
        amount = settings.reserve()
        for key, ceiling in [
            ("global", settings.max_calls),
            (str(claim.session_id), settings.session_calls),
        ]:
            db.execute(
                insert(ModelBudget)
                .values(key=key, calls=0, reserved_usd="0")
                .on_conflict_do_nothing()
            )
            budget = db.scalar(select(ModelBudget).where(ModelBudget.key == key).with_for_update())
            if budget.calls >= ceiling or (
                key == "global" and Decimal(budget.reserved_usd) + amount > settings.budget_usd
            ):
                raise ExtractionFailure("budget_exhausted")
            budget.calls += 1
            budget.reserved_usd = str(Decimal(budget.reserved_usd) + amount)
        job.call_count += 1
        job.reserved_usd = str(Decimal(job.reserved_usd or "0") + amount)


def validated_output(output, claim, document):
    if not isinstance(output, ExtractionResult):
        output = ExtractionResult.model_validate(output)
    validate_context(
        output,
        job_id=str(claim.id),
        revision_id=str(claim.revision_id),
        document_pages={str(document.id): document.page_count},
    )
    if len(output.model_dump_json()) > 32768 or len(output.issues) > 20:
        raise ValueError("Bounded A1 output required")
    if any(
        issue.field not in {*FIELDS, "receipt", "documents", "classification"}
        for issue in output.issues
    ):
        raise ValueError("Unknown issue field")
    if len(output.documentFindings) != 1 or output.documentFindings[0].documentId != str(
        document.id
    ):
        raise ValueError("Exactly the supplied receipt finding is required")
    if output.resultState == "complete" and (
        not output.documentFindings[0].readable
        or output.documentFindings[0].apparentRole != "receipt"
    ):
        raise ValueError("Complete extraction requires a readable final receipt")
    facts = {key: field.value for key, field in vars(output.commonFields).items()}
    facts["category"] = output.classification.value
    facts["mealType"] = output.categoryFields.mealType.value if output.categoryFields else None
    check_facts(facts)
    return output, facts


def prepare_calculation(engine, facts, policy, adapter):
    if (
        any(not facts.get(key) for key in REQUIRED)
        or facts.get("category") != "meals"
        or policy is None
    ):
        return None
    day = date.fromisoformat(facts["receiptDate"])
    if day < policy.effective_date:
        return None
    with Session(engine) as db:
        observation = saved(db, facts["transactionCurrency"], day)
    if observation is None:
        observation = adapter.fetch(facts["transactionCurrency"], day)
    observation = validate_observation(observation, facts["transactionCurrency"], day)
    return policy.calculate(facts, observation)


def finish_expense(
    engine,
    claim,
    *,
    output=None,
    facts=None,
    diagnostics=None,
    calculation=None,
    policy=None,
    failure=None,
    transient=False,
    now=None,
):
    now = now or datetime.now(UTC)
    with Session(engine) as db, db.begin():
        owner = db.scalar(
            select(DemoSession).where(DemoSession.id == claim.session_id).with_for_update()
        )
        job = db.scalar(select(ExpenseJob).where(ExpenseJob.id == claim.id).with_for_update())
        if (
            job is None
            or job.state != "processing"
            or job.lease_token != claim.token
            or job.lease_until <= now
        ):
            return False
        item = db.scalar(select(Expense).where(Expense.id == claim.expense_id).with_for_update())
        if (
            item.revision_id != claim.revision_id
            or owner.expires_at <= now
            or owner.active_persona != "employee"
            or item.state == "excluded"
        ):
            job.state, job.failure_code = "failed", "stale_or_expired"
        elif failure:
            if transient and job.attempts < 3:
                job.state, item.state = "queued", "queued"
                job.available_at = now + timedelta(seconds=2**job.attempts)
            else:
                job.state, item.state = "failed", "failed"
            job.failure_code = item.failure_code = failure
        else:
            if output is not None:
                db.add(
                    ExtractionSuggestion(
                        job_id=job.id,
                        revision_id=claim.revision_id,
                        output=output.model_dump(),
                        diagnostics=diagnostics,
                        created_at=now,
                    )
                )
                item.issues = [
                    issue.model_dump()
                    for issue in output.issues
                    if issue.field not in item.locks
                    or issue.reason in {"multipleReceipts", "unreadable"}
                ]
                item.facts = {**facts, **{key: item.facts.get(key) for key in item.locks}}
                provenance = {
                    key: {
                        "source": "model",
                        "model": MODEL,
                        "promptVersion": PROMPT_VERSION,
                        "schemaVersion": "0.1",
                        "evidenceRefs": (
                            output.classification
                            if key == "category"
                            else output.categoryFields.mealType
                            if key == "mealType" and output.categoryFields
                            else getattr(output.commonFields, key, None)
                        ).model_dump()["evidenceRefs"],
                    }
                    for key in FIELDS
                    if key not in item.locks and (key != "mealType" or output.categoryFields)
                }
                item.provenance = {**item.provenance, **provenance}
            item.failure_code = None
            item.calculation = calculation
            if output and output.resultState in {"unsupported", "couldNotRead"}:
                item.state = "unsupported" if output.resultState == "unsupported" else "unreadable"
                item.calculation = None
            elif item.facts.get("category") not in {None, "meals"}:
                item.state, item.calculation = "unsupported", None
            elif (
                item.issues
                or any(not item.facts.get(key) for key in REQUIRED)
                or (item.locks and not item.confirmed)
            ):
                item.state, item.calculation = "needs_information", None
            elif (
                policy is None
                or date.fromisoformat(item.facts["receiptDate"]) < policy.effective_date
            ):
                item.state, item.calculation = "policy_inactive", None
            elif calculation is None:
                item.state = "conversion_pending"
            else:
                item.state = "review"
                calculation = {**calculation, "expenseRevisionId": str(claim.revision_id)}
                item.calculation = calculation
                db.execute(
                    insert(ExpenseCalculation)
                    .values(revision_id=claim.revision_id, result=calculation, created_at=now)
                    .on_conflict_do_nothing()
                )
                db.execute(
                    insert(MealPolicyVersion)
                    .values(
                        id=policy.version,
                        effective_date=policy.effective_date,
                        rounding=policy.rounding,
                        facts={"caps": CAPS, "clauses": CLAUSES},
                        created_at=now,
                    )
                    .on_conflict_do_nothing()
                )
                fx = calculation["fx"]
                if fx["provider"] != "native":
                    db.execute(
                        insert(FxObservation)
                        .values(
                            currency=fx["currency"],
                            rate_date=date.fromisoformat(fx["date"]),
                            provider=fx["provider"],
                            rate=fx["rate"],
                            source=fx["source"],
                            observed_at=now,
                        )
                        .on_conflict_do_nothing()
                    )
            # Owner lock serializes conflict detection with edits/selection and other job writes.
            if (
                item.state != "excluded"
                and item.facts.get("category") == "meals"
                and item.facts.get("mealType")
                and item.facts.get("receiptDate")
            ):
                others = db.scalars(
                    select(Expense).where(
                        Expense.session_id == item.session_id,
                        Expense.id != item.id,
                        Expense.state != "excluded",
                    )
                ).all()
                conflicts = [
                    other
                    for other in others
                    if other.facts.get("category") == "meals"
                    and all(
                        other.facts.get(key) == item.facts[key]
                        for key in ["receiptDate", "mealType"]
                    )
                ]
                if conflicts:
                    for conflict in [item, *conflicts]:
                        conflict.state, conflict.calculation = "conflict", None
            job.state, job.failure_code = "complete", None
        job.lease_token = job.lease_until = None
        return True


def run_expense_once(engine, settings, extractor, policy, fx):
    claim = claim_expense(engine)
    if claim is None:
        return False
    try:
        with Session(engine) as db:
            _, item = authority(db, claim)
            document = db.get(Document, item.document_id)
            raw = db.get(DocumentBytes, document.id).content
            if document.state != "validated" or hashlib.sha256(raw).hexdigest() != document.sha256:
                raise ExtractionFailure("processing_failed")
            context = {
                "schemaVersion": "0.1",
                "jobId": str(claim.id),
                "expenseRevisionId": str(claim.revision_id),
                "submissionCurrency": "GBP",
                "supportedTaxonomy": {"meals": ["breakfast", "lunch", "dinner"]},
                "documents": [
                    {
                        "documentId": str(document.id),
                        "role": "receipt",
                        "mimeType": document.mime_type,
                        "pageCount": document.page_count,
                    }
                ],
                "lockedHumanFields": {key: item.facts.get(key) for key in item.locks},
                "categoryOverride": item.facts.get("category")
                if "category" in item.locks
                else None,
            }
            facts, locks, confirmed = dict(item.facts), list(item.locks), item.confirmed
            bundle = [
                {
                    "id": str(document.id),
                    "content": raw,
                    "mime": document.mime_type,
                    "pages": document.page_count,
                }
            ]
        output, diagnostics = None, None
        if claim.kind == "extract":
            reserve_call(engine, claim, settings)
            output, diagnostics = extractor.extract(context, bundle)
            try:
                output, candidate = validated_output(output, claim, document)
            except ValueError:
                raise ExtractionFailure("invalid_output") from None
            facts = {**candidate, **{key: facts.get(key) for key in locks}}
        check_facts(facts)
        # Revalidate before a new FX provider read, not only before persistence.
        with Session(engine) as db:
            authority(db, claim)
        calculation = None
        if (not locks or confirmed) and (
            output is None
            or output.resultState in {"complete", "needsInformation"}
            and not output.issues
        ):
            try:
                calculation = prepare_calculation(engine, facts, policy, fx)
            except FxPending:
                pass
        finish_expense(
            engine,
            claim,
            output=output,
            facts=facts,
            diagnostics=diagnostics,
            calculation=calculation,
            policy=policy,
        )
        if diagnostics:
            observe(diagnostics)
    except ExtractionFailure as error:
        finish_expense(engine, claim, failure=error.code, transient=error.transient)
    except Exception:
        finish_expense(engine, claim, failure="processing_failed", transient=True)
    return True
