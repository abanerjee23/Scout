"""Mixed categories on real PostgreSQL; fake extraction is not model-quality evidence."""

from copy import deepcopy

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from unloop.category_fields import cabin
from unloop.contracts import CategoryExtractionResult, validate_context
from unloop.meal_policy import MealPolicy
from unloop.models import Expense
from unloop.policy_registry import registry
from unloop.worker import run_once

from backend.tests.test_evidence import image_bytes, upload
from backend.tests.test_meals import FACTS, TEST_POLICY, output, run
from backend.tests.test_meals import meal as meal

AIR = {
    "category": "air",
    "merchant": "Synthetic Airline",
    "originalAmount": "125.25",
    "journeyType": "return",
    "origin": "LHR",
    "destination": "CDG",
    "departureDate": "2026-10-02",
    "returnDate": "2026-10-04",
    "cabinClass": "economy",
}
GROUND = {
    "category": "groundTransport",
    "merchant": "Synthetic Taxi",
    "originalAmount": "32.50",
    "transportType": "taxi",
    "origin": None,
    "destination": None,
    "businessJourney": "yes",
    "penaltyAmount": "2.50",
}
POLICY = MealPolicy.load(
    {
        "MEAL_POLICY_APPROVED": "true",
        "MEAL_POLICY_EFFECTIVE_DATE": "2026-01-01",
        "MEAL_POLICY_ROUNDING": "ROUND_HALF_UP_LINE",
        "GROUND_POLICY_APPROVED": "true",
    }
)


class CategoryExtractor:
    def __init__(self, facts):
        self.facts = facts
        self.calls = []

    def extract(self, context, documents):
        self.calls.append(deepcopy(context))
        result = output(context, documents[0])
        result["schemaVersion"] = "0.2"

        def field(value, support=None):
            found = output(context, support or documents[0], {"merchant": value})["commonFields"][
                "merchant"
            ]
            return found

        values = {**FACTS, **self.facts}
        result["classification"] = field(values["category"])
        result["commonFields"] = {key: field(values[key]) for key in result["commonFields"]}
        names = {
            "air": [
                "journeyType",
                "origin",
                "destination",
                "departureDate",
                "returnDate",
                "cabinClass",
            ],
            "groundTransport": [
                "transportType",
                "origin",
                "destination",
                "businessJourney",
                "penaltyAmount",
            ],
        }[values["category"]]
        result["categoryFields"] = {
            key: field(values.get(key), documents[-1] if key == "cabinClass" else None)
            for key in names
        }
        result["documentFindings"] += [
            {"documentId": item["id"], "readable": True, "apparentRole": "supportingDocument"}
            for item in documents[1:]
        ]
        return result, {"model": "explicit_fake", "outcome": "complete"}


def saved(client, meal):
    return client.get(f"/api/expenses/{meal[3]['id']}").json()


def test_air_grade_cabin_and_no_amount_cap(client, postgres, meal):
    assert run(postgres, CategoryExtractor(AIR), policy=POLICY)
    result = saved(client, meal)
    assert result["state"] == "review"
    assert result["calculation"]["claimGbp"] == "125.25"
    assert result["calculation"]["findings"][0]["maximumCabin"] == "economy"
    assert "mealType" not in result["facts"]
    assert "AIR-04" in result["assessment"]["requiredRules"]


def test_air_above_grade_cannot_become_reviewable(client, postgres, meal):
    assert run(postgres, CategoryExtractor({**AIR, "cabinClass": "business"}), policy=POLICY)
    result = saved(client, meal)
    assert result["state"] == "noncompliant"
    assert result["calculation"]["eligible"] is False
    assert result["calculation"]["claimGbp"] == "0.00"
    assert client.get(f"/api/reports/{meal[0]}/expenses").json()["preparedClaimGbp"] == "0.00"


def test_air_self_declared_cabin_requires_matching_evidence(client, postgres, meal):
    assert run(postgres, CategoryExtractor({**AIR, "cabinClass": "business"}), policy=POLICY)
    response = client.patch(
        f"/api/expenses/{meal[3]['id']}",
        headers=meal[1],
        json={"version": 1, "facts": {"cabinClass": "economy"}, "confirmed": True},
    )
    assert response.status_code == 200
    assert run(postgres, policy=POLICY)
    result = saved(client, meal)
    assert result["state"] == "needs_information"
    assert result["question"]["field"] == "cabinClass"
    assert result["calculation"]["eligible"] is False


def test_ground_optional_route_penalty_and_owner_activation(client, postgres, meal):
    assert run(postgres, CategoryExtractor(GROUND))
    result = saved(client, meal)
    assert result["state"] == "policy_inactive"
    assert "GROUND-01" not in {value["id"] for value in registry(TEST_POLICY)["clauses"]}
    assert (
        client.post(
            f"/api/expenses/{meal[3]['id']}/recheck", headers=meal[1], json={"version": 1}
        ).status_code
        == 200
    )
    assert run(postgres, policy=POLICY)
    result = saved(client, meal)
    assert result["state"] == "review"
    assert result["calculation"]["claimGbp"] == "30.00"
    assert result["calculation"]["excessGbp"] == "2.50"
    assert result["facts"]["origin"] is None


def test_air_supporting_confirmation_bound_to_report_and_revision(client, postgres, meal):
    assert run(postgres, CategoryExtractor(AIR), policy=POLICY)
    doc = upload(
        client,
        meal[0],
        meal[1],
        content=image_bytes("JPEG"),
        mime="image/jpeg",
        name="confirmation.jpg",
    ).json()["documents"][0]["id"]
    assert run_once(postgres[1])
    response = client.put(
        f"/api/expenses/{meal[3]['id']}/supporting-evidence",
        headers=meal[1],
        json={"version": 1, "documentIds": [doc]},
    )
    assert response.status_code == 200, response.text
    fake = CategoryExtractor(AIR)
    assert run(postgres, fake, policy=POLICY)
    result = saved(client, meal)
    assert result["state"] == "review"
    assert len(fake.calls[0]["documents"]) == 2
    assert (
        result["provenance"]["factEvidence"]["cabinClass"]["evidenceRefs"][0]["documentId"] == doc
    )
    assert (
        client.put(
            f"/api/expenses/{meal[3]['id']}/supporting-evidence",
            headers=meal[1],
            json={"version": 1, "documentIds": []},
        ).status_code
        == 409
    )


def test_category_change_deactivates_old_fields(client, postgres, meal):
    assert run(postgres, CategoryExtractor(AIR), policy=POLICY)
    response = client.patch(
        f"/api/expenses/{meal[3]['id']}",
        headers=meal[1],
        json={
            "version": 1,
            "facts": {"category": "meals", "mealType": "dinner"},
            "confirmed": True,
        },
    )
    assert response.status_code == 200
    assert run(postgres, policy=POLICY)
    result = saved(client, meal)
    assert result["state"] == "review"
    assert "cabinClass" not in result["facts"]
    assert "returnDate" not in result["facts"]
    assert result["calculation"]["claimGbp"] == "50.00"
    with Session(postgres[1]) as db:
        item = db.scalar(select(Expense).where(Expense.id == meal[3]["id"]))
        assert "cabinClass" not in item.facts


@pytest.mark.parametrize(
    "label,expected",
    [
        ("Coach", "economy"),
        ("Economy class", "economy"),
        ("Premium Economy", "premiumEconomy"),
        ("Business class", "business"),
        ("Comfort Plus", None),
    ],
)
def test_cabin_mapping_requires_known_vocabulary(label, expected):
    assert cabin(label) == expected


def test_new_schema_refuses_category_mix_and_outside_references():
    context = {"jobId": "job", "expenseRevisionId": "revision"}
    doc = {"id": "receipt"}
    data, _ = CategoryExtractor(AIR).extract(context, [doc])
    validated = CategoryExtractionResult.model_validate(data)
    validate_context(validated, job_id="job", revision_id="revision", document_pages={"receipt": 1})
    data["categoryFields"]["cabinClass"]["evidenceRefs"][0]["documentId"] = "other-session"
    with pytest.raises(ValueError):
        validate_context(
            CategoryExtractionResult.model_validate(data),
            job_id="job",
            revision_id="revision",
            document_pages={"receipt": 1},
        )
    data["classification"]["value"] = "meals"
    with pytest.raises(ValueError):
        CategoryExtractionResult.model_validate(data)


@pytest.mark.parametrize(
    "grade,cabin_class,eligible",
    [
        ("A", "economy", True),
        ("C", "premiumEconomy", False),
        ("D", "premiumEconomy", True),
        ("F", "business", False),
        ("G", "business", True),
        (None, "economy", False),
    ],
)
def test_cabin_entitlement_table_and_missing_grade(grade, cabin_class, eligible):
    facts = {**FACTS, **AIR, "cabinClass": cabin_class}
    observation = {
        "currency": "GBP",
        "date": "2026-10-01",
        "provider": "native",
        "rate": "1",
        "source": "native",
    }
    result = POLICY.calculate(
        facts,
        observation,
        grade=grade,
        evidence={
            "cabinClass": {
                "value": cabin_class,
                "evidenceRefs": [{"documentId": "receipt", "pageNumber": 1, "snippet": "Cabin"}],
            }
        },
    )
    assert result["eligible"] is eligible
    if grade is None:
        assert result["state"] == "profile_incomplete"
