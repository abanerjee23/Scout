"""Trusted immutable Meal facts; draft activation never inferred from environment presence."""

from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

CAPS = {"breakfast": "15.00", "lunch": "25.00", "dinner": "50.00"}
CLAUSES = ["MEAL-03", "MEAL-04", "MEAL-05", "MEAL-06", "CUR-03"]


@dataclass(frozen=True)
class MealPolicy:
    effective_date: date
    rounding: str
    version: str
    ground_approved: bool = False

    @classmethod
    def load(cls, values):
        if values.get("MEAL_POLICY_APPROVED") != "true":
            return None
        if values.get("MEAL_POLICY_ROUNDING") != "ROUND_HALF_UP_LINE":
            raise ValueError("An explicit reviewed Meal rounding convention is required")
        try:
            effective = date.fromisoformat(values["MEAL_POLICY_EFFECTIVE_DATE"])
        except (KeyError, ValueError):
            raise ValueError("An explicit reviewed Meal effective date is required") from None
        ground = values.get("GROUND_POLICY_APPROVED") == "true"
        version = (
            "synthetic-te-0.3:" if ground else "synthetic-meals-0.2:"
        ) + effective.isoformat()
        return cls(effective, "ROUND_HALF_UP_LINE", version, ground)

    def calculate(self, facts, observation, *, grade=None, evidence=None):
        if date.fromisoformat(facts["receiptDate"]) < self.effective_date:
            return None
        amount, rate = Decimal(facts["originalAmount"]), Decimal(observation["rate"])
        full = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if facts["category"] != "meals":
            return self.calculate_travel(facts, observation, full, grade, evidence or {})
        cap = Decimal(CAPS[facts["mealType"]])
        claim = min(full, cap)
        return {
            "fullGbp": str(full),
            "claimGbp": str(claim),
            "excessGbp": str(full - claim),
            "limitGbp": str(cap),
            "outcome": "Adjusted to policy limit" if full > cap else "Within Meal limit",
            "clauses": CLAUSES,
            "policyVersion": self.version,
            "rounding": self.rounding,
            "fx": observation,
        }

    def calculate_travel(self, facts, observation, full, grade, evidence):
        from unloop.category_fields import cabin

        category = facts["category"]
        clauses = ["GEN-01", "GEN-02", "GEN-05", "CUR-01", "CUR-02", "CUR-03"]
        eligible, outcome, state = True, "Compliant", "review"
        claim = full
        findings = []
        if category == "air":
            clauses += ["AIR-01", "AIR-02", "AIR-03", "AIR-04", "AIR-05"]
            order = ["economy", "premiumEconomy", "business"]
            maximum = {
                **dict.fromkeys("ABC", "economy"),
                **dict.fromkeys("DEF", "premiumEconomy"),
                "G": "business",
            }.get(grade)
            booked = cabin(facts.get("cabinClass"))
            supported = cabin(evidence.get("cabinClass", {}).get("value")) == booked and bool(
                evidence.get("cabinClass", {}).get("evidenceRefs")
            )
            if maximum is None:
                eligible, outcome, state = (
                    False,
                    "Employee profile incomplete",
                    "profile_incomplete",
                )
            elif booked is None or not supported:
                eligible, outcome, state = False, "Cabin evidence required", "needs_information"
            elif order.index(booked) > order.index(maximum):
                eligible, outcome, state = (
                    False,
                    "Noncompliant: cabin exceeds trusted grade allowance",
                    "noncompliant",
                )
            findings.append(
                {
                    "rule": "AIR-03",
                    "bookedCabin": booked,
                    "maximumCabin": maximum,
                    "evidenceSupported": supported,
                    "outcome": outcome,
                }
            )
            if not eligible:
                claim = Decimal("0.00")
        elif category == "groundTransport":
            if self.ground_approved:
                clauses += ["GROUND-01", "GROUND-02", "GROUND-03"]
            if not self.ground_approved:
                eligible, outcome, state = (
                    False,
                    "Ground Transport policy not approved",
                    "policy_inactive",
                )
                claim = Decimal("0.00")
            elif facts.get("businessJourney") != "yes":
                eligible, outcome, state = (
                    False,
                    "Noncompliant: business journey not established",
                    "noncompliant",
                )
                claim = Decimal("0.00")
            else:
                penalty = (Decimal(facts["penaltyAmount"]) * Decimal(observation["rate"])).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )
                claim = max(Decimal("0.00"), full - penalty)
                outcome = "Penalty excluded" if penalty else "Compliant"
            findings.append({"rule": "GROUND-02", "outcome": outcome})
        else:
            raise ValueError("Unsupported policy category")
        return {
            "fullGbp": str(full),
            "claimGbp": str(claim),
            "excessGbp": str(full - claim),
            "limitGbp": None,
            "outcome": outcome,
            "clauses": clauses,
            "policyVersion": self.version,
            "rounding": self.rounding,
            "fx": observation,
            "eligible": eligible,
            "state": state,
            "findings": findings,
            "requiredRules": clauses,
        }
