"""A1 v0.1 Meal output schema; no model or workflow writes."""

from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal["air", "meals", "groundTransport"]
MealType = Literal["breakfast", "lunch", "dinner"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class EvidenceRef(StrictModel):
    documentId: str = Field(min_length=1)
    pageNumber: int = Field(ge=1)
    snippet: str = Field(min_length=1)


class FieldResult(StrictModel):
    state: Literal["supported", "ambiguous", "notFound", "notApplicable"]
    value: str | None
    basis: Literal["explicit", "derived"] | None
    evidenceRefs: list[EvidenceRef]
    note: str | None

    @model_validator(mode="after")
    def check_support(self):
        if self.state == "supported":
            if not self.value or not self.evidenceRefs or self.basis is None:
                raise ValueError("Supported facts need a value, basis and evidence")
        elif self.value is not None:
            raise ValueError("Unresolved fields must not carry a chosen value")
        if self.state in {"notFound", "notApplicable"} and self.evidenceRefs:
            raise ValueError("Absent/inapplicable facts must not claim evidence")
        return self


class CommonFields(StrictModel):
    merchant: FieldResult
    receiptDate: FieldResult
    originalAmount: FieldResult
    transactionCurrency: FieldResult
    vatAmount: FieldResult

    @model_validator(mode="after")
    def validate_values(self):
        if self.receiptDate.value:
            parsed = date.fromisoformat(self.receiptDate.value)
            if parsed.isoformat() != self.receiptDate.value:
                raise ValueError("Use YYYY-MM-DD dates")
        for field in (self.originalAmount, self.vatAmount):
            if field.value:
                try:
                    amount = Decimal(field.value)
                except InvalidOperation as exc:
                    raise ValueError("Amount must be a decimal string") from exc
                if not amount.is_finite() or amount < 0:
                    raise ValueError("Amount must be finite and nonnegative")
        if self.originalAmount.value and Decimal(self.originalAmount.value) <= 0:
            raise ValueError("Receipt amount must be positive")
        if self.vatAmount.value and self.originalAmount.value:
            if Decimal(self.vatAmount.value) > Decimal(self.originalAmount.value):
                raise ValueError("VAT cannot exceed receipt total")
        currency = self.transactionCurrency.value
        if currency and (
            len(currency) != 3
            or not currency.isascii()
            or not currency.isupper()
            or not currency.isalpha()
        ):
            raise ValueError("Currency must be a three-letter uppercase code")
        # Membership in supported ISO currencies is an application gate in Phase 2.
        return self


class MealFields(StrictModel):
    mealType: FieldResult

    @model_validator(mode="after")
    def validate_meal(self):
        if self.mealType.value and self.mealType.value not in {"breakfast", "lunch", "dinner"}:
            raise ValueError("Unknown meal type")
        return self


class Issue(StrictModel):
    field: str
    reason: Literal[
        "missingRequired",
        "ambiguousEvidence",
        "conflictingEvidence",
        "multipleReceipts",
        "unsupportedCategory",
        "unreadable",
    ]
    evidenceRefs: list[EvidenceRef]


class DocumentFinding(StrictModel):
    documentId: str
    readable: bool
    apparentRole: Literal["receipt", "supportingDocument", "unknown"]


class ExtractionResult(StrictModel):
    schemaVersion: Literal["0.1"]
    jobId: str = Field(min_length=1)
    expenseRevisionId: str = Field(min_length=1)
    resultState: Literal["complete", "needsInformation", "unsupported", "couldNotRead"]
    documentFindings: list[DocumentFinding]
    classification: FieldResult
    commonFields: CommonFields
    categoryFields: MealFields | None
    issues: list[Issue]

    @model_validator(mode="after")
    def check_complete(self):
        category = self.classification.value
        if category and category not in {"air", "meals", "groundTransport"}:
            raise ValueError("Unknown category")
        if category != "meals" and self.categoryFields is not None:
            raise ValueError("Only Meal-specific fields are implemented in this slice")
        if category in {"air", "groundTransport"} and self.resultState != "unsupported":
            raise ValueError("Air and Ground Transport processing arrives in Phase 3")
        if self.resultState == "complete":
            required = [
                self.classification,
                self.commonFields.merchant,
                self.commonFields.receiptDate,
                self.commonFields.originalAmount,
                self.commonFields.transactionCurrency,
            ]
            if self.categoryFields is None:
                raise ValueError("Complete Meal output needs category fields")
            required.append(self.categoryFields.mealType)
            if any(f.state != "supported" for f in required) or self.issues:
                raise ValueError("Complete means every required field is supported, without issues")
        return self


def validate_context(
    result: ExtractionResult, *, job_id: str, revision_id: str, document_pages: dict[str, int]
) -> None:
    """Application acceptance gates; valid references do not prove factual accuracy."""
    if result.jobId != job_id or result.expenseRevisionId != revision_id:
        raise ValueError("Stale or mismatched job/revision")
    if not result.documentFindings:
        raise ValueError("Document findings are required")
    for finding in result.documentFindings:
        if finding.documentId not in document_pages:
            raise ValueError("Unknown document finding")
    fields = [
        result.classification,
        *[getattr(result.commonFields, name) for name in CommonFields.model_fields],
    ]
    if result.categoryFields:
        fields.append(result.categoryFields.mealType)
    refs = [ref for field in fields for ref in field.evidenceRefs]
    refs.extend(ref for issue in result.issues for ref in issue.evidenceRefs)
    for ref in refs:
        if ref.documentId not in document_pages or ref.pageNumber > document_pages[ref.documentId]:
            raise ValueError("Evidence points outside the authorised document bundle")
