"""Offline checks of fixture labels; this is not a model evaluation."""

import argparse
import json
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

from pydantic import Field, model_validator

from unloop.contracts import StrictModel

ROOT = Path(__file__).resolve().parents[2]
LIMITS = {"breakfast": Decimal("15"), "lunch": Decimal("25"), "dinner": Decimal("50")}


class FixtureEvidence(StrictModel):
    documentId: str
    pageNumber: int = Field(ge=1)
    lineNumber: int = Field(ge=1)
    snippet: str


class FixtureDocument(StrictModel):
    documentId: str
    source: str
    pageCount: int = Field(ge=1)


class Facts(StrictModel):
    merchant: str | None
    receiptDate: str | None
    originalAmount: str | None
    transactionCurrency: str | None
    vatAmount: str | None
    mealType: str | None


class Fx(StrictModel):
    rate: str
    rateDate: str
    source: str


class Context(StrictModel):
    employeeId: str
    category: str
    fx: Fx | None
    duplicateUpload: bool


class Expected(StrictModel):
    fields: Facts
    evidence: dict[str, list[FixtureEvidence]]
    status: str
    fullReceiptGbp: str | None
    claimGbp: str | None
    excessGbp: str | None
    issue: str | None

    @model_validator(mode="after")
    def values(self):
        if self.status not in {
            "Needs information",
            "Conversion pending",
            "Compliant",
            "Adjusted to policy limit",
        }:
            raise ValueError("Unknown expected status")
        if self.fields.mealType not in {None, *LIMITS}:
            raise ValueError("Invalid meal label")
        if self.fields.receiptDate:
            date.fromisoformat(self.fields.receiptDate)
        for value in [
            self.fields.originalAmount,
            self.fields.vatAmount,
            self.fullReceiptGbp,
            self.claimGbp,
            self.excessGbp,
        ]:
            if value is not None:
                number = Decimal(value)
                if not number.is_finite() or number < 0:
                    raise ValueError("Financial labels must be finite and nonnegative")
        return self


class Case(StrictModel):
    id: str
    scenario: str
    documents: list[FixtureDocument]
    context: Context
    expected: Expected


class Dataset(StrictModel):
    datasetVersion: str
    split: str
    cases: list[Case]


def load_dataset(split: str, root: Path = ROOT) -> Dataset:
    return Dataset.model_validate_json(
        (root / "fixtures" / "meals" / split / "cases.json").read_text()
    )


def validate_case(case: Case, root: Path = ROOT) -> None:
    docs = {d.documentId: d for d in case.documents}
    if len(docs) != len(case.documents) or not docs:
        raise ValueError(f"{case.id}: documents missing or identifiers duplicated")
    for doc in docs.values():
        source = (root / doc.source).resolve()
        source.relative_to((root / "fixtures" / "meals").resolve())
        if not source.is_file():
            raise ValueError(f"{case.id}: missing source")
    for field in Facts.model_fields:
        value = getattr(case.expected.fields, field)
        refs = case.expected.evidence.get(field, [])
        if (value is not None) != bool(refs):
            raise ValueError(f"{case.id}: evidence/value mismatch for {field}")
        for ref in refs:
            if ref.documentId not in docs:
                raise ValueError(f"{case.id}: invented document")
            doc = docs[ref.documentId]
            lines = (root / doc.source).read_text().splitlines()
            if ref.pageNumber > doc.pageCount or ref.lineNumber > len(lines):
                raise ValueError(f"{case.id}: invalid evidence location")
            if lines[ref.lineNumber - 1] != ref.snippet:
                raise ValueError(f"{case.id}: snippet mismatch")
            if field == "vatAmount" and not ref.snippet.startswith("VAT "):
                raise ValueError(f"{case.id}: VAT evidence must identify explicit VAT")
    expected = case.expected
    fields = expected.fields
    if expected.status in {"Needs information", "Conversion pending"}:
        if expected.claimGbp is not None or expected.excessGbp is not None or not expected.issue:
            raise ValueError(f"{case.id}: blocked case cannot contain a claim")
        return
    required = [
        fields.merchant,
        fields.receiptDate,
        fields.originalAmount,
        fields.transactionCurrency,
        fields.mealType,
    ]
    if any(v is None for v in required) or expected.issue is not None:
        raise ValueError(f"{case.id}: a claim needs complete facts")
    if fields.transactionCurrency == "GBP":
        full = Decimal(fields.originalAmount)
    else:
        fx = case.context.fx
        if fx is None or fx.rateDate != fields.receiptDate or Decimal(fx.rate) <= 0:
            raise ValueError(f"{case.id}: expected claim has no matching-date FX")
        full = Decimal(fields.originalAmount) * Decimal(fx.rate)
    # Fixtures deliberately use exact pennies: no unapproved rounding rule is encoded.
    if full != full.quantize(Decimal("0.01")):
        raise ValueError(f"{case.id}: fixture depends on an unapproved rounding rule")
    claim = min(full, LIMITS[fields.mealType])
    excess = full - claim
    if (full, claim, excess) != tuple(
        Decimal(v) for v in (expected.fullReceiptGbp, expected.claimGbp, expected.excessGbp)
    ):
        raise ValueError(f"{case.id}: expected financial labels do not reconcile")
    status = "Adjusted to policy limit" if excess else "Compliant"
    if status != expected.status:
        raise ValueError(f"{case.id}: expected status disagrees with cap")


def check_all(root: Path = ROOT) -> dict:
    seen: set[str] = set()
    source_sets: dict[str, set[str]] = {}
    summary: dict = {"kind": "fixture-integrity-only", "modelRuns": 0, "splits": {}}
    for split in ("development", "heldout"):
        dataset = load_dataset(split, root)
        if dataset.split != split or dataset.datasetVersion != "0.1" or len(dataset.cases) != 12:
            raise ValueError(f"{split}: expected 12 cases in dataset v0.1")
        source_sets[split] = set()
        for case in dataset.cases:
            if case.id in seen:
                raise ValueError("Case IDs must be unique across splits")
            seen.add(case.id)
            validate_case(case, root)
            source_sets[split].update(d.source for d in case.documents)
        summary["splits"][split] = dict(Counter(c.expected.status for c in dataset.cases))
    if source_sets["development"] & source_sets["heldout"]:
        raise ValueError("Receipt source files overlap across splits")
    summary["cases"] = len(seen)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(check_all(), indent=2))


if __name__ == "__main__":
    main()
