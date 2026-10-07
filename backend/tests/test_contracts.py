from copy import deepcopy

import pytest
from pydantic import ValidationError
from unloop.contracts import ExtractionResult, validate_context


def supported(value):
    return {
        "state": "supported",
        "value": value,
        "basis": "explicit",
        "evidenceRefs": [{"documentId": "receipt-1", "pageNumber": 1, "snippet": str(value)}],
        "note": None,
    }


@pytest.fixture
def candidate():
    return {
        "schemaVersion": "0.1",
        "jobId": "job-1",
        "expenseRevisionId": "rev-1",
        "resultState": "complete",
        "documentFindings": [
            {"documentId": "receipt-1", "readable": True, "apparentRole": "receipt"}
        ],
        "classification": supported("meals"),
        "commonFields": {
            "merchant": supported("Example Kitchen"),
            "receiptDate": supported("2026-09-21"),
            "originalAmount": supported("62.00"),
            "transactionCurrency": supported("GBP"),
            "vatAmount": {
                "state": "notFound",
                "value": None,
                "basis": None,
                "evidenceRefs": [],
                "note": None,
            },
        },
        "categoryFields": {"mealType": supported("dinner")},
        "issues": [],
    }


def test_full_receipt_value_and_absent_vat_validate(candidate):
    result = ExtractionResult.model_validate(candidate)
    validate_context(result, job_id="job-1", revision_id="rev-1", document_pages={"receipt-1": 1})
    assert result.commonFields.originalAmount.value == "62.00"
    assert result.commonFields.vatAmount.value is None


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-1", "0", "not money"])
def test_bad_amounts_rejected(candidate, bad):
    candidate["commonFields"]["originalAmount"] = supported(bad)
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(candidate)


def test_complete_cannot_hide_missing_meal(candidate):
    candidate["categoryFields"]["mealType"] = {
        "state": "notFound",
        "value": None,
        "basis": None,
        "evidenceRefs": [],
        "note": None,
    }
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(candidate)


def test_unsupported_guess_and_extra_financial_outputs_rejected(candidate):
    for field in ({"state": "ambiguous"}, {"evidenceRefs": []}):
        changed = deepcopy(candidate)
        changed["commonFields"]["originalAmount"].update(field)
        with pytest.raises(ValidationError):
            ExtractionResult.model_validate(changed)
    candidate["claimGbp"] = "50.00"
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(candidate)


def test_context_rejects_stale_and_forged_refs(candidate):
    result = ExtractionResult.model_validate(candidate)
    with pytest.raises(ValueError, match="revision"):
        validate_context(
            result, job_id="job-1", revision_id="rev-2", document_pages={"receipt-1": 1}
        )
    candidate["commonFields"]["originalAmount"]["evidenceRefs"][0]["documentId"] = "private-2"
    result = ExtractionResult.model_validate(candidate)
    with pytest.raises(ValueError, match="authorised"):
        validate_context(
            result, job_id="job-1", revision_id="rev-1", document_pages={"receipt-1": 1}
        )


def test_other_categories_cannot_be_complete_in_meal_slice(candidate):
    candidate["classification"] = supported("air")
    with pytest.raises(ValidationError):
        ExtractionResult.model_validate(candidate)
