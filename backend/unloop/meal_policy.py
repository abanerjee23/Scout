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
        return cls(effective, "ROUND_HALF_UP_LINE", "synthetic-meals-0.2:" + effective.isoformat())

    def calculate(self, facts, observation):
        if date.fromisoformat(facts["receiptDate"]) < self.effective_date:
            return None
        amount, rate = Decimal(facts["originalAmount"]), Decimal(observation["rate"])
        full = (amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
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
