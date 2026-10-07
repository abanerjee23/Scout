"""Score explicit synthetic A1 outputs; never read user corrections or call a provider.

Labels are loaded only by this scorer, never by the model input builder. Held-out
release scoring is explicit; any later tuning exposure requires a recorded replacement set.
"""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from unloop.contracts import ExtractionResult, validate_context
from unloop.fixture_check import load_dataset

ROOT = Path(__file__).resolve().parents[1]
GATES = ROOT / "docs/validation/PHASE_2_RELEASE_GATES.json"
REQUIRED = ["merchant", "receiptDate", "originalAmount", "transactionCurrency", "mealType"]
CRITICAL = {"originalAmount", "transactionCurrency", "receiptDate"}


def score(outputs, cases):
    exact = total = critical = pauses = expected_pauses = valid = readable = useful = 0
    for case in cases:
        record = outputs.get(case.id)
        expected = case.expected.fields
        total += sum(getattr(expected, key) is not None for key in REQUIRED)
        needs_pause = any(
            getattr(expected, key) is None for key in REQUIRED
        ) or case.expected.issue in {"multipleReceipts", "ambiguousEvidence", "unreadable"}
        expected_pauses += needs_pause
        readable += not needs_pause
        if record is None:
            continue
        try:
            result = ExtractionResult.model_validate(record)
            validate_context(
                result,
                job_id=result.jobId,
                revision_id=result.expenseRevisionId,
                document_pages={doc.documentId: doc.pageCount for doc in case.documents},
            )
        except ValueError:
            continue
        valid += 1
        actual = {
            key: getattr(result.commonFields, key).value for key in REQUIRED if key != "mealType"
        }
        actual["mealType"] = result.categoryFields.mealType.value if result.categoryFields else None
        complete = result.resultState == "complete"
        for key in REQUIRED:
            label, value = getattr(expected, key), actual.get(key)
            if label is not None:
                matches = value == label
                if key == "originalAmount" and value is not None:
                    matches = Decimal(value) == Decimal(label)
                exact += matches
                critical += key in CRITICAL and not matches and complete
            elif key in CRITICAL and value is not None and complete:
                critical += 1
        if needs_pause:
            pauses += not complete
        else:
            useful += complete
    return {
        "providedCases": len(outputs),
        "scoredCases": valid,
        "schemaValid": valid,
        "requiredFieldExact": exact,
        "requiredFieldDenominator": total,
        "criticalWrongAcceptedFinancialFacts": critical,
        "appropriatePauses": pauses,
        "pauseDenominator": expected_pauses,
        "readableReviewable": useful,
        "readableDenominator": readable,
        "isLiveModelProof": False,
        "latencyCost": "not_supplied",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validate-gates", action="store_true")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--release-heldout", action="store_true")
    args = parser.parse_args()
    gates = json.loads(GATES.read_text())
    if args.validate_gates:
        print(
            json.dumps(
                {
                    "status": "gates_frozen",
                    "version": gates["gateVersion"],
                    "quality": "unmeasured",
                    "providerCalls": 0,
                }
            )
        )
        return
    if not args.results or args.split == "heldout" and not args.release_heldout:
        parser.error(
            "Explicit synthetic results required; held-out scoring requires --release-heldout"
        )
    try:
        records = json.loads(args.results.read_text())
        result = score(records, load_dataset(args.split).cases)
        print(json.dumps(result, sort_keys=True))
    except Exception:
        parser.exit(1, "Synthetic result scoring failed; no input or exception details logged.\n")


if __name__ == "__main__":
    main()
