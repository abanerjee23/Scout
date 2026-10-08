"""Publish scored, frozen synthetic results as Arize AX experiments; never run a model.

The default is a local preview. --upload is an explicit separate action. Model inputs
and expected labels remain separate; no user corrections, receipts or sessions are read.
"""

import argparse
import contextlib
import json
import logging
import os
import re
from pathlib import Path

from unloop.fixture_check import load_dataset
from unloop.meal_policy import MealPolicy
from unloop.observability import ArizeSettings, safe_metadata
from unloop.policy_questions import PolicyAnswer
from unloop.policy_registry import registry

from scripts import meal_eval, policy_eval

POLICY_METRICS = ("fullyCorrect", "citationsValid", "humanReviewed", "criticalFalsePermission")
MEAL_METRICS = (
    "schemaValid",
    "requiredFieldExactRatio",
    "criticalWrongAcceptedFinancialFacts",
    "appropriatePause",
    "readableReviewable",
)


def safe_answer(record):
    try:
        return PolicyAnswer.model_validate(record.get("result", {})).model_dump()
    except ValueError:
        return {"state": "invalid"}


def policy_runs(records, cases, source):
    summary = policy_eval.score(records, cases, source)
    index = {(value["caseId"], value["mode"]): value for value in records}
    rows = []
    for case in cases:
        for mode in policy_eval.MODES:
            record = index.get((case["id"], mode))
            scored = policy_eval.score([record] if record else [], [case], source)["modes"][mode]
            review = record.get("humanReview", {}) if record else {}
            rows.append(
                {
                    **(safe_metadata(record.get("diagnostics", {})) if record else {}),
                    "caseId": case["id"],
                    "mode": mode,
                    "question": case["question"],
                    "policyVersion": source["version"],
                    # Only the answer schema enters an experiment; extra input fields are discarded.
                    "output": safe_answer(record) if record else {"state": "missing"},
                    "fullyCorrect": scored["fullyCorrect"],
                    "citationsValid": scored["citationsValid"],
                    "humanReviewed": scored["humanReviewed"],
                    "criticalFalsePermission": scored["criticalFalsePermission"],
                    "criticalReviewStatus": "reviewed"
                    if type(review.get("falsePermission")) is bool
                    else "unreviewed",
                    "caseCritical": case["critical"],
                    "evidenceBasis": "supplied_synthetic_outputs_with_explicit_human_review",
                    "isLiveModelProof": False,
                }
            )
    return rows, summary


def meal_runs(records, cases):
    if set(records) - {case.id for case in cases}:
        raise ValueError("Unknown synthetic case")
    summary = meal_eval.score(records, cases)
    rows = []
    for case in cases:
        result = records.get(case.id)
        scored = meal_eval.score({case.id: result} if result else {}, [case])
        denominator = scored["requiredFieldDenominator"]
        # Store scoring results, not receipt bytes or unvalidated extraction payloads.
        rows.append(
            {
                "caseId": case.id,
                "output": {"state": "provided" if result else "missing"},
                "schemaValid": scored["schemaValid"],
                "requiredFieldExactRatio": scored["requiredFieldExact"] / denominator
                if denominator
                else 0,
                "criticalWrongAcceptedFinancialFacts": scored[
                    "criticalWrongAcceptedFinancialFacts"
                ],
                "appropriatePause": scored["appropriatePauses"],
                "pauseExpected": bool(scored["pauseDenominator"]),
                "readableReviewable": scored["readableReviewable"],
                "evidenceBasis": "supplied_synthetic_extraction_outputs",
                "isLiveModelProof": False,
            }
        )
    return rows, summary


def prepare(suite, records, *, split="development", release_heldout=False, policy=None):
    if split not in {"development", "heldout"}:
        raise ValueError("Unknown split")
    if split == "heldout" and not release_heldout:
        raise ValueError("Held-out exposure requires explicit release")
    if suite == "policy":
        if policy is None:
            raise ValueError("Reviewed policy configuration is required")
        rows, summary = policy_runs(records, policy_eval.load(split), registry(policy))
    elif suite == "meal":
        rows, summary = meal_runs(records, load_dataset(split).cases)
    else:
        raise ValueError("Unknown evaluation suite")
    if suite == "policy":
        summary["qualityGatePassed"] = summary["pairedComplete"] and all(
            value["qualityGatePassed"] for value in summary["modes"].values()
        )
    else:
        gates = json.loads(meal_eval.GATES.read_text())
        summary["qualityGatePassed"] = (
            summary["schemaValid"] == len(rows)
            and summary["criticalWrongAcceptedFinancialFacts"] == 0
            and summary["requiredFieldExact"] / summary["requiredFieldDenominator"]
            >= float(gates["requiredFieldAccuracyMinimum"])
            and summary["appropriatePauses"] == summary["pauseDenominator"]
            and (
                summary["readableReviewable"] / summary["readableDenominator"]
                if summary["readableDenominator"]
                else 0
            )
            >= float(gates["readableReviewableMinimum"])
        )
    for row in rows:
        row["split"] = split
        row["datasetVersion"] = "policy-1" if suite == "policy" else "0.1"
        row["comparisonGatePassed"] = summary["qualityGatePassed"]
        if suite == "policy":
            row["sourceHash"] = registry(policy)["sourceHash"]
    return {
        "suite": suite,
        "split": split,
        "runs": rows,
        "summary": summary,
        "providerCalls": 0,
        "isLiveModelProof": False,
    }


def publish(packet, name, settings, *, client=None):
    """Only explicit synthetic packets are accepted; no provider tasks or judges run."""
    from arize import ArizeClient, Region
    from arize.experiments.evaluators.types import EvaluationResultFieldNames
    from arize.experiments.types import ExperimentTaskFieldNames

    if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", name):
        raise ValueError("Invalid experiment name")
    metrics = POLICY_METRICS if packet["suite"] == "policy" else MEAL_METRICS
    client = client or ArizeClient(
        api_key=settings.key,
        region=Region.UNSET if settings.region == "us" else Region(settings.region),
        enable_caching=False,
    )
    experiment = client.experiments.create(
        name=name,
        space=settings.space,
        experiment_runs=packet["runs"],
        task_fields=ExperimentTaskFieldNames(output="output"),
        evaluator_columns={key: EvaluationResultFieldNames(score=key) for key in metrics},
        force_http=True,
    )
    if not getattr(experiment, "id", None):
        raise ValueError("Arize did not confirm experiment creation")
    return experiment


def _upload_child(packet, name, settings, queue):
    with (
        open(os.devnull, "w") as sink,
        contextlib.redirect_stdout(sink),
        contextlib.redirect_stderr(sink),
    ):
        logging.disable(logging.CRITICAL)
        try:
            publish(packet, name, settings)
            queue.put("uploaded")
        except Exception:
            queue.put("unavailable")


def upload(packet, name, settings):
    import multiprocessing

    context = multiprocessing.get_context("spawn")
    queue = context.Queue()
    child = context.Process(target=_upload_child, args=(packet, name, settings, queue))
    try:
        child.start()
        child.join(timeout=30)
        if child.is_alive() or queue.get(timeout=0.1) != "uploaded":
            raise RuntimeError("Upload not confirmed")
    finally:
        if child.is_alive():
            child.kill()
            child.join(timeout=1)
        queue.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", choices=["meal", "policy"], required=True)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--split", choices=["development", "heldout"], default="development")
    parser.add_argument("--release-heldout", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional local synthetic experiment packet")
    parser.add_argument("--upload", action="store_true")
    parser.add_argument("--name", help="Unique experiment name, required for --upload")
    args = parser.parse_args()
    if args.upload and not args.name:
        parser.error("An explicit unique --name is required for upload")
    try:
        if args.results.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Synthetic results exceed the import bound")
        packet = prepare(
            args.suite,
            json.loads(args.results.read_text()),
            split=args.split,
            release_heldout=args.release_heldout,
            policy=MealPolicy.load(os.environ),
        )
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                json.dump(packet, stream, indent=2)
        if args.upload:
            settings = ArizeSettings.load(os.environ, require_enabled=False)
            if settings is None:
                raise ValueError("Arize credentials are not configured")
            try:
                upload(packet, args.name, settings)
            except Exception:
                parser.exit(
                    1, "Arize upload not confirmed; inspect the experiment name before retrying.\n"
                )
        print(
            json.dumps(
                {
                    "status": "uploaded" if args.upload else "local_preview",
                    "suite": packet["suite"],
                    "split": packet["split"],
                    "runs": len(packet["runs"]),
                    "summary": packet["summary"],
                    "providerCalls": 0,
                    "isLiveModelProof": False,
                }
            )
        )
    except Exception:
        parser.exit(1, "Arize evaluation import stopped; no input or exception details logged.\n")


if __name__ == "__main__":
    main()
