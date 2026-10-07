import pytest
from unloop.fixture_check import check_all, load_dataset, validate_case


def test_fixture_counts_evidence_and_expected_arithmetic():
    result = check_all()
    assert result["cases"] == 24
    assert result["modelRuns"] == 0


def test_fixture_harness_detects_receipt_overwrite():
    case = load_dataset("development").cases[2].model_copy(deep=True)
    case.expected.fields.originalAmount = "50.00"
    with pytest.raises(ValueError, match="reconcile"):
        validate_case(case)


def test_fixture_harness_detects_claim_on_missing_info():
    case = load_dataset("development").cases[3].model_copy(deep=True)
    case.expected.claimGbp = "15.00"
    with pytest.raises(ValueError, match="blocked"):
        validate_case(case)


def test_fixture_harness_detects_bad_evidence():
    case = load_dataset("development").cases[0].model_copy(deep=True)
    case.expected.evidence["merchant"][0].snippet = "Invented restaurant"
    with pytest.raises(ValueError, match="snippet"):
        validate_case(case)


def test_vat_evidence_cannot_be_a_substring_of_the_total():
    case = load_dataset("development").cases[6].model_copy(deep=True)
    case.expected.evidence["vatAmount"] = case.expected.evidence["originalAmount"]
    with pytest.raises(ValueError, match="explicit VAT"):
        validate_case(case)
