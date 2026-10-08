"""An unscored/forged answer cannot satisfy the frozen policy release comparison."""

from copy import deepcopy

import pytest
from unloop.meal_policy import MealPolicy
from unloop.policy_registry import registry

from scripts.policy_eval import inputs, load, score

POLICY = MealPolicy.load(
    {
        "MEAL_POLICY_APPROVED": "true",
        "MEAL_POLICY_EFFECTIVE_DATE": "2026-10-01",
        "MEAL_POLICY_ROUNDING": "ROUND_HALF_UP_LINE",
    }
)


def test_policy_model_inputs_never_contain_expected_labels():
    for split in ["development", "heldout"]:
        cases = load(split)
        assert len(cases) == 12 and len(inputs(cases)) == 24
        assert all(set(value) == {"caseId", "question", "mode"} for value in inputs(cases))


def test_missing_human_review_and_missing_pair_cannot_pass_gate():
    case = load("development")[0]
    source = registry(POLICY)
    clause = next(value for value in source["clauses"] if value["id"] == "MEAL-04")
    record = {
        "caseId": case["id"],
        "mode": "rag",
        "policyVersion": source["version"],
        "result": {
            "state": "answered",
            "answer": "Breakfast is £15.",
            "citations": [{"clauseId": "MEAL-04", "quote": clause["text"][:80]}],
        },
    }
    result = score([record], [case], source)
    assert result["pairedComplete"] is False
    assert result["modes"]["rag"]["citationsValid"] == 1
    assert result["modes"]["rag"]["qualityGatePassed"] is False
    assert result["modes"]["rag"]["latencyP95Ms"] is None
    assert result["modes"]["rag"]["estimatedCostUsd"] is None
    with pytest.raises(ValueError):
        score([record, record], [case], source)
    bad = deepcopy(record)
    bad["humanReview"] = {"fullyCorrect": True, "falsePermission": False}
    bad["result"]["citations"][0]["quote"] = "Invented blanket permission"
    assert score([bad], [case], source)["modes"]["rag"]["fullyCorrect"] == 0


def test_critical_false_permission_blocks_even_human_fully_correct_mark():
    case = load("development")[1]
    source = registry(POLICY)
    record = {
        "caseId": case["id"],
        "mode": "rag",
        "policyVersion": source["version"],
        "humanReview": {"fullyCorrect": True, "falsePermission": True},
        "result": {
            "state": "answered",
            "answer": "Incorrect permission.",
            "citations": [
                {
                    "clauseId": id,
                    "quote": next(value for value in source["clauses"] if value["id"] == id)[
                        "text"
                    ][:80],
                }
                for id in case["expectedClauseIds"]
            ],
        },
    }
    result = score([record], [case], source)["modes"]["rag"]
    assert result["criticalFalsePermission"] == 1 and result["qualityGatePassed"] is False
