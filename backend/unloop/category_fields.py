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


def blocking_issue(field, reason, facts):
    # Optional values do not become mandatory when a model reports them missing.
    # Ambiguous/malformed evidence still pauses for review.
    return not (
        field == "vatAmount"
        or facts.get("category") == "groundTransport"
        and field in {"origin", "destination"}
        and reason == "missingRequired"
    )


# Deliberately small fixture-backed aliases, not an airport directory.
# A city name never implies a particular airport.
LOCATION_ALIASES = {
    "lhr": "LHR",
    "heathrow": "LHR",
    "london heathrow": "LHR",
    "cdg": "CDG",
    "charles de gaulle": "CDG",
    "paris charles de gaulle": "CDG",
    "london": "London",
    "paris": "Paris",
    "new york": "New York",
}


def normalize_locations(facts):
    if facts.get("category") != "air":
        return facts
    result = dict(facts)
    for key in ["origin", "destination"]:
        if result.get(key):
            text = " ".join(result[key].split())
            result[key] = LOCATION_ALIASES.get(text.lower(), text)
    return result
