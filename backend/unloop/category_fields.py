"""Versioned category vocabulary and required facts; unrelated fields are inactive."""

COMMON = ["category", "merchant", "receiptDate", "originalAmount", "transactionCurrency"]
CATEGORY_FIELDS = {
    "meals": ["mealType"],
    "air": ["journeyType", "origin", "destination", "departureDate", "returnDate", "cabinClass"],
    "groundTransport": [
        "transportType",
        "origin",
        "destination",
        "businessJourney",
        "penaltyAmount",
    ],
}
ALL_FIELDS = list(dict.fromkeys([*COMMON, "vatAmount", *sum(CATEGORY_FIELDS.values(), [])]))
CABIN_ALIASES = {
    "economy": "economy",
    "economy class": "economy",
    "coach": "economy",
    "premium economy": "premiumEconomy",
    "premiumeconomy": "premiumEconomy",
    "business": "business",
    "business class": "business",
}


def cabin(value):
    return CABIN_ALIASES.get((value or "").strip().lower())


def required(facts):
    category = facts.get("category")
    specific = {
        "meals": ["mealType"],
        "air": ["journeyType", "origin", "destination", "departureDate", "cabinClass"],
        "groundTransport": ["transportType", "businessJourney", "penaltyAmount"],
    }.get(category, [])
    if category == "air" and facts.get("journeyType") == "return":
        specific = [*specific, "returnDate"]
    return [*COMMON, *specific]


def active_fields(facts):
    fields = [*COMMON, "vatAmount", *CATEGORY_FIELDS.get(facts.get("category"), [])]
    if facts.get("journeyType") != "return":
        fields = [key for key in fields if key != "returnDate"]
    return fields
