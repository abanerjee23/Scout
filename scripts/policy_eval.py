"""Frozen, paired policy scorer: semantic human review plus exact citations; no providers."""

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from unloop.meal_policy import MealPolicy
from unloop.policy_index import GuidanceUnavailable
from unloop.policy_questions import accept_answer
from unloop.policy_registry import registry

ROOT = Path(__file__).resolve().parents[1]
MODES = ("rag", "fullContext")


def load(split):
    return json.loads((ROOT / "fixtures/policy" / split / "cases.json").read_text())["cases"]


def inputs(cases):
    return [
        {"caseId": case["id"], "question": case["question"], "mode": mode}
        for case in cases
        for mode in MODES
    ]


def score(records, cases, source):
    index = {(record["caseId"], record["mode"]): record for record in records}
    if len(index) != len(records):
        raise ValueError("Duplicate comparison record")
    allowed = {(case["id"], mode) for case in cases for mode in MODES}
    if set(index) - allowed:
        raise ValueError("Unknown comparison record")
    summary = {}
    for mode in MODES:
        correct = cited = reviewed = false_permission = critical_reviewed = 0
        times, costs = [], []
        for case in cases:
            record = index.get((case["id"], mode), {})
            review = record.get("humanReview", {})
            reviewed += type(review.get("fullyCorrect")) is bool
            critical_reviewed += case["critical"] and type(review.get("falsePermission")) is bool
            false_permission += case["critical"] and review.get("falsePermission") is True
            try:
                answer = accept_answer(record["result"], source["clauses"])
                if record["policyVersion"] != source["version"]:
                    raise ValueError("Wrong policy version")
                ids = {value["clauseId"] for value in answer["citations"]}
                valid = set(case["expectedClauseIds"]) <= ids
                if not case["expectedClauseIds"]:
                    valid = answer["state"] == "notCovered"
                cited += valid
                correct += (
                    valid
                    and review.get("fullyCorrect") is True
                    and review.get("falsePermission") is not True
                )
            except (KeyError, ValueError, TypeError, GuidanceUnavailable):
                # Invalid records never count as correct; private details stay out of output.
                pass
            diagnostics = record.get("diagnostics", {})
            if type(diagnostics.get("latencyMs")) in (int, float) and diagnostics["latencyMs"] >= 0:
                times.append(diagnostics["latencyMs"])

            try:
                cost = Decimal(diagnostics["estimatedCostUsd"])
                if cost.is_finite() and cost >= 0:
                    costs.append(cost)
            except (KeyError, InvalidOperation, TypeError):
                pass
        critical_count = sum(case["critical"] for case in cases)
        summary[mode] = {
            "caseDenominator": len(cases),
            "provided": sum((case["id"], mode) in index for case in cases),
            "fullyCorrect": correct,
            "citationsValid": cited,
            "humanReviewed": reviewed,
            "criticalReviewed": critical_reviewed,
            "criticalDenominator": critical_count,
            "criticalFalsePermission": false_permission,
            "qualityGatePassed": correct / len(cases) >= 0.9
            and false_permission == 0
            and critical_reviewed == critical_count,
            "latencySamples": len(times),
            "latencyP95Ms": sorted(times)[max(0, (len(times) * 95 + 99) // 100 - 1)]
            if times
            else None,
            "costSamples": len(costs),
            "estimatedCostUsd": str(sum(costs)) if costs else None,
        }
    return {
        "modes": summary,
        "pairedComplete": set(index) == allowed,
        "isLiveModelProof": False,
        "basis": "supplied outputs and explicit human review; no provider run attestation",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inputs", action="store_true")
    parser.add_argument("--results", type=Path)
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--release-heldout", action="store_true")
    parser.add_argument("--effective-date", default="2026-10-01")
    args = parser.parse_args()
    if args.split == "heldout" and not args.release_heldout:
        parser.error("Held-out exposure requires --release-heldout")
    cases = load(args.split)
    if args.inputs:
        print(json.dumps(inputs(cases), indent=2))
        return
    if not args.results:
        parser.error("Provide supplied comparison results or --inputs")
    policy = MealPolicy.load(
        {
            "MEAL_POLICY_APPROVED": "true",
            "MEAL_POLICY_EFFECTIVE_DATE": args.effective_date,
            "MEAL_POLICY_ROUNDING": "ROUND_HALF_UP_LINE",
        }
    )
    print(
        json.dumps(score(json.loads(args.results.read_text()), cases, registry(policy)), indent=2)
    )


if __name__ == "__main__":
    main()
