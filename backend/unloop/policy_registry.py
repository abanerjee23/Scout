"""Trusted packaged clauses; source activation is an explicit owner configuration."""

import hashlib
import json
from importlib.resources import files

from fastapi import APIRouter, Request

from unloop.api import Owner

router = APIRouter(prefix="/api")
CHECKLISTS = {
    "meals": [
        "GEN-01",
        "GEN-02",
        "GEN-04",
        "GEN-05",
        "MEAL-01",
        "MEAL-02",
        "MEAL-03",
        "MEAL-04",
        "MEAL-05",
        "MEAL-06",
        "CUR-01",
        "CUR-02",
        "CUR-03",
    ],
    "air": [
        "GEN-01",
        "GEN-02",
        "GEN-05",
        "AIR-01",
        "AIR-02",
        "AIR-03",
        "AIR-04",
        "AIR-05",
        "CUR-01",
        "CUR-02",
        "CUR-03",
    ],
    "groundTransport": [
        "GEN-01",
        "GEN-02",
        "GEN-05",
        "GROUND-01",
        "GROUND-02",
        "GROUND-03",
        "CUR-01",
        "CUR-02",
        "CUR-03",
    ],
}


def registry(policy):
    if policy is None:
        return {
            "status": "inactive",
            "version": None,
            "clauses": [],
            "message": "Policy awaits owner activation.",
        }
    data = json.loads(files("unloop").joinpath("policy_clauses.json").read_text())
    selected = [
        value
        for key, value in data.items()
        if policy.ground_approved or not key.startswith("GROUND-")
    ]
    digest = hashlib.sha256(json.dumps(selected, sort_keys=True).encode()).hexdigest()
    return {
        "status": "active",
        "version": policy.version,
        "effectiveDate": policy.effective_date.isoformat(),
        "sourceId": "synthetic-travel-expense",
        "sourceHash": digest,
        "clauses": selected,
        "groundTransportActive": policy.ground_approved,
        "rounding": policy.rounding,
        "precedence": "Governing policy overrides explanatory FAQ. Only one version is active.",
    }


def explain(calculation, category):
    if calculation is None:
        return None
    return {
        "version": calculation["policyVersion"],
        "outcome": calculation["outcome"],
        "clauses": calculation["clauses"],
        "requiredRules": CHECKLISTS[category],
        "method": "Code-owned rule checks and Decimal arithmetic",
        "canApprove": False,
        "message": calculation["outcome"],
    }


@router.get("/policy")
def read_policy(request: Request, _owner: Owner):
    return registry(request.app.state.meal_policy)


def store_policy(db, policy):
    from datetime import UTC, datetime

    from sqlalchemy.dialects.postgresql import insert

    from unloop.models import MealPolicyVersion

    source = registry(policy)
    db.execute(
        insert(MealPolicyVersion)
        .values(
            id=policy.version,
            effective_date=policy.effective_date,
            rounding=policy.rounding,
            facts={"source": source},
            created_at=datetime.now(UTC),
        )
        .on_conflict_do_nothing()
    )
    saved = db.get(MealPolicyVersion, policy.version)
    if saved.facts.get("source", {}).get("sourceHash") != source["sourceHash"]:
        raise ValueError("An existing policy version cannot be replaced by amended sources")
    return saved.facts["source"]
