import pytest
from pydantic import ValidationError
from unloop.database import Settings, postgres_engine
from unloop.intake import ReportHeader, parse_report


@pytest.mark.parametrize(
    "dates, start, end",
    [
        ("1–4 October 2026", "2026-10-01", "2026-10-04"),
        ("2026-10-01 to 2026-10-04", "2026-10-01", "2026-10-04"),
        ("30 September 2026 to 4 October 2026", "2026-09-30", "2026-10-04"),
        ("4 October 2026", "2026-10-04", "2026-10-04"),
    ],
)
def test_explicit_natural_date_formats(dates, start, end):
    result = parse_report(f"Prepare my London expense report for {dates} for a client workshop.")
    assert result["ready"]
    assert result["header"] == {
        "name": "London expense report",
        "startDate": start,
        "endDate": end,
        "businessPurpose": "a client workshop",
    }
    assert result["parser"] == "deterministic-v1"


@pytest.mark.parametrize(
    "dates",
    [
        "1–4 October",
        "next week",
        "03/04/2026",
        "29 February 2025",
        "4–1 October 2026",
        "2026-10-01 to 4 October",
        "1 October to 4 October 2026",
    ],
)
def test_ambiguous_missing_or_invalid_dates_need_review(dates):
    result = parse_report(f"Prepare my London expense report for {dates} for a client workshop.")
    assert not result["ready"]
    assert not result["header"]["startDate"]


def test_missing_purpose_is_question_not_invented():
    result = parse_report("Prepare my London expense report for 1–4 October 2026")
    assert result["header"]["businessPurpose"] == ""
    assert "business purpose" in " ".join(result["questions"])
    assert "manager" not in str(result).lower()


def test_single_day_to_attend_is_purpose_not_an_incomplete_date_range():
    result = parse_report("Prepare my London expense report for 2026-10-01 to attend a workshop.")
    assert result["ready"]
    assert result["header"]["startDate"] == result["header"]["endDate"] == "2026-10-01"
    assert result["header"]["businessPurpose"] == "a workshop"


def test_header_rejects_manager_fields_and_grade():
    header = {
        "name": "London",
        "startDate": "2026-10-01",
        "endDate": "2026-10-04",
        "businessPurpose": "Client workshop",
    }
    for field in ("managerEmail", "grade", "sessionId", "employeeId"):
        with pytest.raises(ValidationError):
            ReportHeader.model_validate({**header, field: "untrusted"})


def test_postgres_and_cookie_configuration_fail_closed():
    with pytest.raises(ValueError, match="PostgreSQL"):
        postgres_engine("sqlite://")
    with pytest.raises(ValueError, match="local development"):
        Settings.load({"APP_ORIGIN": "https://example.com", "SESSION_COOKIE_SECURE": "false"})
    with pytest.raises(ValueError):
        Settings.load({"SESSION_TTL_SECONDS": "0"})
