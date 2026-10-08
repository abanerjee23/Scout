"""Actual PostgreSQL Meal invariants; explicit synthetic SDK/FX adapters are not live proof."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text
from unloop.expense_worker import claim_expense, finish_expense, run_expense_once
from unloop.extraction import A1Settings, AgentsExtractor, ExtractionFailure
from unloop.fx import FxPending, HistoricalFx
from unloop.meal_policy import MealPolicy
from unloop.models import Expense, ExpenseJob, ExtractionSuggestion, ModelBudget
from unloop.worker import run_once

from backend.tests.test_contracts import supported
from backend.tests.test_evidence import image_bytes, report_and_headers, upload
from backend.tests.test_gmail import gmail_client as gmail_client

FACTS = {
    "category": "meals",
    "merchant": "Synthetic Kitchen",
    "receiptDate": "2026-10-01",
    "originalAmount": "62.00",
    "transactionCurrency": "GBP",
    "mealType": "dinner",
    "vatAmount": None,
}
TEST_POLICY = MealPolicy.load(
    {
        "MEAL_POLICY_APPROVED": "true",
        "MEAL_POLICY_EFFECTIVE_DATE": "2026-01-01",
        "MEAL_POLICY_ROUNDING": "ROUND_HALF_UP_LINE",
    }
)
TEST_LIMITS = A1Settings(
    "synthetic-not-a-live-key",
    50,
    20,
    Decimal("1"),
    Decimal("0.1"),
    Decimal("0.5"),
    24000,
    4000,
    25,
)


def output(context, document, facts=None):
    values = {**FACTS, **(facts or {})}

    def field(value):
        result = (
            supported(value)
            if value is not None
            else {
                "state": "notFound",
                "value": None,
                "basis": None,
                "evidenceRefs": [],
                "note": None,
            }
        )
        for ref in result["evidenceRefs"]:
            ref["documentId"] = document["id"]
        return result

    return {
        "schemaVersion": "0.1",
        "jobId": context["jobId"],
        "expenseRevisionId": context["expenseRevisionId"],
        "resultState": "complete"
        if all(values.get(key) for key in FACTS if key != "vatAmount")
        else "needsInformation",
        "documentFindings": [
            {"documentId": document["id"], "readable": True, "apparentRole": "receipt"}
        ],
        "classification": field(values["category"]),
        "commonFields": {
            key: field(values[key])
            for key in [
                "merchant",
                "receiptDate",
                "originalAmount",
                "transactionCurrency",
                "vatAmount",
            ]
        },
        "categoryFields": {"mealType": field(values["mealType"])},
        "issues": [],
    }


class FakeExtractor:
    def __init__(self, facts=None, hook=None):
        self.facts, self.hook, self.calls = facts, hook, []

    def extract(self, context, documents):
        self.calls.append((deepcopy(context), documents))
        if self.hook:
            self.hook()
        return output(context, documents[0], self.facts), {
            "model": "explicit_fake",
            "outcome": "complete",
        }


@pytest.fixture
def meal(client, postgres):
    with postgres[1].begin() as db:
        db.execute(text("TRUNCATE model_budgets, fx_observations, meal_policy_versions"))
    report, headers = report_and_headers(client)
    document = upload(client, report, headers).json()["documents"][0]["id"]
    assert run_once(postgres[1])
    response = client.post(
        f"/api/reports/{report}/expenses", headers=headers, json={"documentId": document}
    )
    assert response.status_code == 201, response.text
    return report, headers, document, response.json()["expense"]


def run(postgres, extractor=None, policy=TEST_POLICY, fx=None, settings=TEST_LIMITS):
    return run_expense_once(
        postgres[1], settings, extractor or FakeExtractor(), policy, fx or HistoricalFx()
    )


def test_meal_cap_full_total_missing_vat_and_authoritative_reload(client, postgres, meal):
    report, _, document, item = meal
    fake = FakeExtractor()
    assert run(postgres, fake)
    saved = client.get(f"/api/expenses/{item['id']}").json()
    assert saved["state"] == "review"
    assert saved["facts"]["vatAmount"] is None
    assert saved["calculation"]["fullGbp"] == "62.00"
    assert saved["calculation"]["claimGbp"] == "50.00"
    assert saved["calculation"]["excessGbp"] == "12.00"
    assert "MEAL-04" in saved["calculation"]["clauses"]
    assert client.get(f"/api/reports/{report}/expenses").json()["preparedClaimGbp"] == "50.00"
    assert client.get(f"/api/documents/{document}/original").content == image_bytes()
    assert client.get(f"/api/expenses/{item['id']}").json() == saved
    assert len(fake.calls) == 1
    assert set(fake.calls[0][0]) == {
        "schemaVersion",
        "jobId",
        "expenseRevisionId",
        "submissionCurrency",
        "lockedHumanFields",
        "categoryOverride",
        "documents",
        "supportedTaxonomy",
    }


@pytest.mark.parametrize(
    "kind,amount,claim,excess",
    [
        ("breakfast", "20", "15.00", "5.00"),
        ("lunch", "22", "22.00", "0.00"),
        ("dinner", "62", "50.00", "12.00"),
    ],
)
def test_caps_and_no_allowance_pooling(kind, amount, claim, excess):
    result = TEST_POLICY.calculate(
        {**FACTS, "mealType": kind, "originalAmount": amount}, {"rate": "1"}
    )
    assert (result["claimGbp"], result["excessGbp"]) == (claim, excess)


def test_candidate_decimal_rounding_is_explicit_synthetic_configuration():
    result = TEST_POLICY.calculate({**FACTS, "originalAmount": "1.005"}, {"rate": "1"})
    assert result["fullGbp"] == "1.01"
    assert MealPolicy.load({}) is None
    with pytest.raises(ValueError):
        MealPolicy.load({"MEAL_POLICY_APPROVED": "true"})


def test_inactive_policy_never_calls_fx(client, postgres, meal):
    _, _, _, item = meal
    fx = SimpleNamespace(fetch=lambda *_: pytest.fail("Inactive policy must not call FX"))
    assert run(postgres, FakeExtractor({"transactionCurrency": "EUR"}), policy=None, fx=fx)
    saved = client.get(f"/api/expenses/{item['id']}").json()
    assert saved["state"] == "policy_inactive" and saved["calculation"] is None


def test_locked_human_corrections_survive_rerun_and_only_dependencies_change(
    client, postgres, meal
):
    _, headers, _, item = meal
    assert run(postgres)
    changed = client.patch(
        f"/api/expenses/{item['id']}",
        headers=headers,
        json={
            "version": 1,
            "facts": {"originalAmount": "70.00", "mealType": "lunch"},
            "confirmed": True,
        },
    ).json()
    assert changed["calculation"] is None and changed["version"] == 2
    assert run(postgres)
    saved = client.get(f"/api/expenses/{item['id']}").json()
    assert saved["calculation"]["claimGbp"] == "25.00"
    merchant = client.patch(
        f"/api/expenses/{item['id']}",
        headers=headers,
        json={"version": 2, "facts": {"merchant": "Corrected Merchant"}, "confirmed": True},
    ).json()
    assert {
        key: value
        for key, value in merchant["calculation"].items()
        if key not in {"expenseRevisionId", "derivation"}
    } == {key: value for key, value in saved["calculation"].items() if key != "expenseRevisionId"}
    assert merchant["calculation"]["expenseRevisionId"] == merchant["revisionId"]
    assert merchant["calculation"]["derivation"]["sourceRevisionId"] == saved["revisionId"]
    client.app.state.a1_settings = TEST_LIMITS
    rerun = client.post(f"/api/expenses/{item['id']}/extract", headers=headers, json={"version": 3})
    assert rerun.status_code == 200
    assert run(postgres, FakeExtractor({"originalAmount": "12", "mealType": "dinner"}))
    final = client.get(f"/api/expenses/{item['id']}").json()
    assert final["facts"]["originalAmount"] == "70.00" and final["facts"]["mealType"] == "lunch"
    assert final["facts"]["merchant"] == "Corrected Merchant"
    assert final["provenance"]["originalAmount"]["source"] == "human"
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(ExtractionSuggestion)) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("originalAmount", "NaN"),
        ("originalAmount", "-1"),
        ("originalAmount", "0"),
        ("receiptDate", "2026-02-30"),
        ("receiptDate", "2099-01-01"),
        ("transactionCurrency", "ZZZ"),
        ("vatAmount", "999"),
    ],
)
def test_invalid_human_facts_fail_without_revision(client, postgres, meal, field, value):
    _, headers, _, item = meal
    assert run(postgres)
    response = client.patch(
        f"/api/expenses/{item['id']}",
        headers=headers,
        json={"version": 1, "facts": {field: value}, "confirmed": True},
    )
    assert response.status_code == 422
    assert client.get(f"/api/expenses/{item['id']}").json()["version"] == 1


def test_model_disabled_is_honest_and_no_paid_call(client, postgres, meal):
    _, headers, _, item = meal
    assert run(postgres, FakeExtractor(hook=lambda: pytest.fail("No call allowed")), settings=None)
    saved = client.get(f"/api/expenses/{item['id']}").json()
    assert saved["failureCode"] == "model_unconfigured"
    assert (
        client.post(
            f"/api/expenses/{item['id']}/extract", headers=headers, json={"version": 1}
        ).status_code
        == 503
    )


def test_duplicate_evidence_reuses_one_expense_across_reports(client, postgres, meal):
    report, headers, document, item = meal
    duplicate = client.post(
        f"/api/reports/{report}/expenses", headers=headers, json={"documentId": document}
    ).json()
    assert duplicate["reused"] and duplicate["expense"]["id"] == item["id"]
    other_report, _ = report_and_headers(client)
    same = upload(client, other_report, headers).json()["documents"][0]["id"]
    assert same == document
    result = client.post(
        f"/api/reports/{other_report}/expenses", headers=headers, json={"documentId": same}
    ).json()
    assert result["reused"] and result["expense"]["reportId"] == report
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(Expense)) == 1


def test_stale_job_and_expired_lease_cannot_write(client, postgres, meal):
    _, headers, _, item = meal
    old = claim_expense(postgres[1])
    changed = client.patch(
        f"/api/expenses/{item['id']}",
        headers=headers,
        json={"version": 1, "facts": FACTS, "confirmed": True},
    )
    assert changed.status_code == 200
    assert finish_expense(postgres[1], old, calculation={"claimGbp": "999"}, policy=TEST_POLICY)
    assert client.get(f"/api/expenses/{item['id']}").json()["calculation"] is None
    assert run(postgres)
    current = client.get(f"/api/expenses/{item['id']}").json()
    assert current["calculation"] is None  # stale extraction never established receipt eligibility
    client.app.state.a1_settings = TEST_LIMITS
    assert (
        client.post(
            f"/api/expenses/{item['id']}/extract",
            headers=headers,
            json={"version": current["version"]},
        ).status_code
        == 200
    )
    assert run(postgres)
    assert client.get(f"/api/expenses/{item['id']}").json()["calculation"]["claimGbp"] == "50.00"
    assert not finish_expense(postgres[1], old)


def test_claim_recovery_and_idempotent_finish(postgres, meal):
    first = claim_expense(postgres[1])
    with postgres[1].begin() as db:
        db.execute(
            ExpenseJob.__table__.update().values(
                lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    recovered = claim_expense(postgres[1])
    assert first.token != recovered.token
    assert not finish_expense(postgres[1], first)
    assert finish_expense(postgres[1], recovered, failure="model_unconfigured")
    assert not finish_expense(postgres[1], recovered)


def test_missing_meal_opens_targeted_question(client, postgres, meal):
    _, _, _, item = meal
    assert run(postgres, FakeExtractor({"mealType": None}))
    result = client.get(f"/api/expenses/{item['id']}").json()
    assert result["state"] == "needs_information" and result["question"]["field"] == "mealType"
    assert result["calculation"] is None


def test_budget_reservations_survive_failure_and_prevent_extra_calls(client, postgres, meal):
    class Fail(FakeExtractor):
        def extract(self, *_):
            raise ExtractionFailure("model_timeout", True)

    limits = A1Settings(
        "synthetic", 1, 1, Decimal("1"), Decimal(".1"), Decimal(".5"), 24000, 4000, 25
    )
    assert run(postgres, Fail(), settings=limits)
    with postgres[1].begin() as db:
        db.execute(ExpenseJob.__table__.update().values(available_at=datetime.now(UTC)))
    assert run(
        postgres, FakeExtractor(hook=lambda: pytest.fail("Budget must block")), settings=limits
    )
    with postgres[1].connect() as db:
        assert db.scalar(select(ModelBudget.calls).where(ModelBudget.key == "global")) == 1
        assert db.scalar(select(Expense.failure_code)) == "budget_exhausted"


@pytest.mark.parametrize("returned", ["2026-10-02", "2026-10-03"])
def test_ecb_exact_date_guard_and_fallback_snapshot(monkeypatch, returned):
    from datetime import date

    adapter = HistoricalFx()
    monkeypatch.setattr(
        adapter,
        "request",
        lambda *_: {"date": returned, "base": "EUR", "quote": "GBP", "rate": Decimal(".85033")},
    )
    if returned != "2026-10-03":
        with pytest.raises(FxPending):
            adapter.fetch("EUR", date(2026, 10, 3))
    else:
        assert adapter.fetch("EUR", date(2026, 10, 3))["rate"] == "0.85033"
    adapter.oxr_key = "synthetic-not-live"
    calls = []

    def request(url, params):
        calls.append((url, params))
        if "frankfurter" in url:
            return {"date": "2026-10-02", "base": "EUR", "quote": "GBP", "rate": "1"}
        return {
            "timestamp": 1790985600,
            "base": "USD",
            "rates": {"GBP": Decimal(".8"), "EUR": Decimal("1.2")},
        }

    monkeypatch.setattr(adapter, "request", request)
    assert Decimal(adapter.fetch("EUR", date(2026, 10, 3))["rate"]) == Decimal(".8") / Decimal(
        "1.2"
    )
    assert "base" not in calls[1][1] and "symbols" not in calls[1][1]


def test_cross_report_conflict_requires_explicit_selection(client, postgres, meal):
    first_report, headers, _, first = meal
    assert run(postgres)
    report, _ = report_and_headers(client)
    other = upload(
        client,
        report,
        headers,
        content=image_bytes("JPEG"),
        mime="image/jpeg",
        name="other.jpg",
    ).json()["documents"][0]["id"]
    assert run_once(postgres[1])
    second = client.post(
        f"/api/reports/{report}/expenses", headers=headers, json={"documentId": other}
    ).json()["expense"]
    assert run(postgres, FakeExtractor({"originalAmount": "20"}))
    assert client.get(f"/api/expenses/{first['id']}").json()["state"] == "conflict"
    assert client.get(f"/api/expenses/{second['id']}").json()["calculation"] is None
    assert client.get(f"/api/reports/{first_report}/expenses").json()["preparedClaimGbp"] == "0.00"
    chosen = client.post(
        f"/api/expenses/{second['id']}/choose", headers=headers, json={"version": 1}
    )
    assert chosen.status_code == 200
    assert run(postgres)
    assert client.get(f"/api/expenses/{first['id']}").json()["state"] == "excluded"
    assert client.get(f"/api/expenses/{second['id']}").json()["calculation"]["claimGbp"] == "20.00"


def test_cross_owner_manager_csrf_and_origin_exclusion(client, postgres, meal, app_config):
    from fastapi.testclient import TestClient
    from unloop import create_app

    from backend.tests.test_evidence import ORIGIN

    report, headers, document, item = meal
    with TestClient(create_app(app_config), base_url=ORIGIN) as other:
        _, foreign_headers = report_and_headers(other)
        assert other.get(f"/api/expenses/{item['id']}").status_code == 404
        assert other.get(f"/api/reports/{report}/expenses").status_code == 404
        assert (
            other.patch(
                f"/api/expenses/{item['id']}",
                headers=foreign_headers,
                json={"version": 1, "facts": FACTS},
            ).status_code
            == 404
        )
    assert (
        client.patch(
            f"/api/expenses/{item['id']}", headers={"Origin": ORIGIN}, json={"version": 1}
        ).status_code
        == 403
    )
    assert (
        client.patch(
            f"/api/expenses/{item['id']}",
            headers={**headers, "Origin": "https://evil.invalid"},
            json={"version": 1},
        ).status_code
        == 403
    )
    client.patch("/api/session/persona", headers=headers, json={"persona": "manager"})
    assert client.get(f"/api/expenses/{item['id']}").status_code == 403
    assert client.get(f"/api/reports/{report}/expenses").status_code == 403
    assert (
        client.post(
            f"/api/reports/{report}/expenses", headers=headers, json={"documentId": document}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("change", ["revision", "persona", "expiry"])
def test_no_db_locks_over_model_and_fresh_authority_blocks_result(client, postgres, meal, change):
    from concurrent.futures import ThreadPoolExecutor

    report, headers, _, item = meal

    def during_call():
        with ThreadPoolExecutor() as pool:
            assert (
                pool.submit(client.get, f"/api/reports/{report}").result(timeout=2).status_code
                == 200
            )
            if change == "revision":
                assert (
                    pool.submit(
                        client.patch,
                        f"/api/expenses/{item['id']}",
                        headers=headers,
                        json={"version": 1, "facts": {"merchant": "Human"}},
                    )
                    .result(timeout=2)
                    .status_code
                    == 200
                )
            elif change == "persona":
                assert (
                    pool.submit(
                        client.patch,
                        "/api/session/persona",
                        headers=headers,
                        json={"persona": "manager"},
                    )
                    .result(timeout=2)
                    .status_code
                    == 200
                )
            else:
                with postgres[1].begin() as db:
                    db.execute(
                        text(
                            "UPDATE demo_sessions SET created_at=now()-interval '2 days', "
                            "expires_at=now()-interval '1 day'"
                        )
                    )

    assert run(postgres, FakeExtractor(hook=during_call))
    with postgres[1].connect() as db:
        assert db.scalar(select(Expense.calculation)) is None
        assert db.scalar(select(func.count()).select_from(ExtractionSuggestion)) == 0


@pytest.mark.parametrize("bad", ["job", "reference", "date", "currency", "amount", "role"])
def test_model_outputs_fail_contract_authority(client, postgres, meal, bad):
    class Bad(FakeExtractor):
        def extract(self, context, documents):
            value, metrics = super().extract(context, documents)
            if bad == "job":
                value["jobId"] = "wrong"
            elif bad == "reference":
                value["commonFields"]["originalAmount"]["evidenceRefs"][0]["documentId"] = (
                    "another-owner"
                )
            elif bad == "role":
                value["documentFindings"][0]["apparentRole"] = "supportingDocument"
            else:
                field = {
                    "date": "receiptDate",
                    "currency": "transactionCurrency",
                    "amount": "originalAmount",
                }[bad]
                value["commonFields"][field]["value"] = {
                    "date": "2026-02-30",
                    "currency": "ZZZ",
                    "amount": "NaN",
                }[bad]
            return value, metrics

    assert run(postgres, Bad())
    with postgres[1].connect() as db:
        assert db.scalar(select(Expense.calculation)) is None
        assert db.scalar(select(Expense.failure_code)) == "invalid_output"


def test_multiple_receipts_issue_does_not_become_permission(client, postgres, meal):
    class Multiple(FakeExtractor):
        def extract(self, context, documents):
            value, metrics = super().extract(context, documents)
            value["resultState"] = "needsInformation"
            value["issues"] = [
                {"field": "receipt", "reason": "multipleReceipts", "evidenceRefs": []}
            ]
            return value, metrics

    assert run(postgres, Multiple())
    report, headers, _, item = meal
    saved = client.get(f"/api/expenses/{item['id']}").json()
    assert saved["state"] == "needs_information" and saved["calculation"] is None
    assert (
        client.patch(
            f"/api/expenses/{item['id']}",
            headers=headers,
            json={"version": 1, "facts": FACTS, "confirmed": True},
        ).status_code
        == 200
    )
    assert run(postgres)
    assert client.get(f"/api/expenses/{item['id']}").json()["state"] == "needs_information"


@pytest.mark.parametrize("rate", ["NaN", "Infinity", "0", "-1", "oops"])
def test_fx_positive_finite_validation(rate):
    from unloop.fx import positive

    with pytest.raises(FxPending):
        positive(rate)


def test_saved_fx_precedence_and_wrong_adapter_date(client, postgres, meal):
    from unloop.models import FxObservation

    with postgres[1].begin() as db:
        for provider, rate, source in [
            ("oxr", ".8", "https://openexchangerates.org/api/historical"),
            ("ecb", ".85", "https://api.frankfurter.dev/v2/providers/ecb"),
        ]:
            from datetime import date

            db.execute(
                FxObservation.__table__.insert().values(
                    currency="EUR",
                    rate_date=date(2026, 10, 1),
                    provider=provider,
                    rate=rate,
                    source=source,
                    observed_at=datetime.now(UTC),
                )
            )
    fx = SimpleNamespace(fetch=lambda *_: pytest.fail("Saved exact ECB observation must win"))
    assert run(postgres, FakeExtractor({"transactionCurrency": "EUR"}), fx=fx)
    saved = client.get(f"/api/expenses/{meal[3]['id']}").json()
    assert saved["calculation"]["fx"]["provider"] == "ecb"
    assert saved["calculation"]["fullGbp"] == "52.70"


def test_async_sdk_receives_only_selected_bytes_and_tracing_disabled(monkeypatch):
    import asyncio

    import agents

    captured = {}

    async def run_sdk(agent, input, **kwargs):
        captured.update(agent=agent, input=input, kwargs=kwargs)
        return "synthetic-result"

    monkeypatch.setattr(agents.Runner, "run", run_sdk)
    adapter = AgentsExtractor(TEST_LIMITS)
    assert (
        asyncio.run(
            adapter.run(
                {"jobId": "job", "expenseRevisionId": "revision"},
                [({"id": "authorized", "mime": "image/png"}, "c3ludGhldGlj")],
            )
        )
        == "synthetic-result"
    )
    assert captured["agent"].tools == []
    assert captured["agent"].model.model == "gpt-6-luna"
    assert captured["kwargs"]["max_turns"] == 1
    assert captured["kwargs"]["run_config"].tracing_disabled
    assert not captured["kwargs"]["run_config"].trace_include_sensitive_data
    assert captured["agent"].model_settings.store is False
    assert captured["input"][0]["content"][2]["image_url"].endswith("c3ludGhldGlj")


def test_concurrent_claims_only_one_worker_and_duplicate_api_create(client, postgres, meal):
    from concurrent.futures import ThreadPoolExecutor

    report, headers, document, item = meal
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: claim_expense(postgres[1]), range(2)))
    assert sum(claim is not None for claim in claims) == 1
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post(
                    f"/api/reports/{report}/expenses",
                    headers=headers,
                    json={"documentId": document},
                ).json(),
                range(2),
            )
        )
    assert {value["expense"]["id"] for value in results} == {item["id"]}


def test_gmail_imported_original_enters_the_same_expense_pipeline(gmail_client, postgres):
    from unloop.gmail import run_scan_once

    from backend.tests.test_gmail import connected, scan

    client, adapter, settings = gmail_client
    report, headers, _ = connected(gmail_client)
    scan(client, report, headers)
    for _ in range(3):
        assert run_scan_once(postgres[1], settings, adapter)
    assert run_once(postgres[1])
    document = client.get(f"/api/reports/{report}/evidence").json()["documents"][0]
    assert document["sources"] == ["gmail"]
    result = client.post(
        f"/api/reports/{report}/expenses", headers=headers, json={"documentId": document["id"]}
    )
    assert result.status_code == 201
    with postgres[1].begin() as db:
        db.execute(text("TRUNCATE model_budgets"))
    assert run(postgres)
    assert (
        client.get(f"/api/expenses/{result.json()['expense']['id']}").json()["calculation"][
            "claimGbp"
        ]
        == "50.00"
    )


def test_unconfirmed_human_uncertainty_does_not_calculate(client, postgres, meal):
    _, headers, _, item = meal
    assert run(postgres, FakeExtractor({"mealType": None}))
    assert (
        client.patch(
            f"/api/expenses/{item['id']}",
            headers=headers,
            json={"version": 1, "facts": {"mealType": "dinner"}, "confirmed": False},
        ).status_code
        == 200
    )
    assert run(postgres)
    saved = client.get(f"/api/expenses/{item['id']}").json()
    assert saved["calculation"] is None and saved["question"]["field"] == "confirmation"


def test_revision_fk_rejects_another_expense_revision(client, postgres, meal):
    from uuid import uuid4

    from sqlalchemy.exc import IntegrityError

    report, headers, _, first = meal
    document = upload(
        client, report, headers, content=image_bytes("JPEG"), mime="image/jpeg", name="other.jpg"
    ).json()["documents"][0]["id"]
    assert run_once(postgres[1])
    second = client.post(
        f"/api/reports/{report}/expenses", headers=headers, json={"documentId": document}
    ).json()["expense"]
    with postgres[1].connect() as db:
        owner = db.scalar(select(Expense.session_id).where(Expense.id == first["id"]))
    with pytest.raises(IntegrityError), postgres[1].begin() as db:
        db.execute(
            ExpenseJob.__table__.insert().values(
                id=uuid4(),
                session_id=owner,
                expense_id=first["id"],
                revision_id=second["revisionId"],
                kind="calculate",
                state="queued",
                attempts=0,
                call_count=0,
                available_at=datetime.now(UTC),
            )
        )


@pytest.mark.parametrize("result_state", ["unsupported", "couldNotRead"])
def test_unsupported_unreadable_are_honest_and_never_financial(
    client, postgres, meal, result_state
):
    class Other(FakeExtractor):
        def extract(self, context, documents):
            value, diagnostics = super().extract(context, documents)
            value["resultState"] = result_state
            return value, diagnostics

    assert run(postgres, Other())
    saved = client.get(f"/api/expenses/{meal[3]['id']}").json()
    assert (
        saved["state"] == {"unsupported": "unsupported", "couldNotRead": "unreadable"}[result_state]
    )
    assert saved["calculation"] is None


def test_expense_original_and_calculation_survive_real_api_process_restart(
    client, postgres, meal, app_config
):
    import socket

    import httpx

    from backend.tests.test_process_restart import api_process

    assert run(postgres)
    _, _, document, item = meal
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    for _ in range(2):
        with (
            api_process(
                app_config["DATABASE_URL"], port, schema=app_config["UNLOOP_TEST_SCHEMA"]
            ) as origin,
            httpx.Client(
                base_url=origin, headers={"Cookie": "unloop_demo=" + client.cookies["unloop_demo"]}
            ) as reopened,
        ):
            saved = reopened.get(f"/api/expenses/{item['id']}").json()
            assert saved["facts"]["originalAmount"] == "62.00"
            assert saved["calculation"]["claimGbp"] == "50.00"
            assert reopened.get(f"/api/documents/{document}/original").content == image_bytes()


def test_real_expense_worker_crash_reclaim_without_paid_calls(client, postgres, meal, app_config):
    import os
    import subprocess
    import sys

    from scripts.postgres_test_support import isolated_schema

    environment = {
        **os.environ,
        "DATABASE_URL": postgres[0],
        "UNLOOP_TEST_SCHEMA": isolated_schema(postgres[1]),
        "A1_ENABLED": "false",
    }
    code = (
        "from unloop.database import Settings,postgres_engine; "
        "from unloop.expense_worker import claim_expense; import os; s=Settings.load(); "
        "e=postgres_engine(s.database_url,schema=s.database_schema); "
        "c=claim_expense(e); os._exit(7 if c else 8)"
    )
    assert (
        subprocess.run(
            [sys.executable, "-c", code],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode
        == 7
    )
    with postgres[1].begin() as db:
        db.execute(
            ExpenseJob.__table__.update().values(
                lease_until=datetime.now(UTC) - timedelta(seconds=1)
            )
        )
    assert (
        subprocess.run(
            [sys.executable, "-m", "unloop.worker", "--queue", "expenses", "--once"],
            env=environment,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        ).returncode
        == 0
    )
    with postgres[1].connect() as db:
        assert db.scalar(select(ExpenseJob.attempts)) == 2
        assert db.scalar(select(Expense.failure_code)) == "model_unconfigured"


def test_migration_populated_upgrade_downgrade_reupgrade_and_immutable_policy(postgres):
    from alembic import command
    from alembic.config import Config
    from sqlalchemy.exc import DBAPIError

    from scripts.postgres_test_support import isolated_database

    with isolated_database(postgres[0]) as (_, engine):
        with engine.begin() as db:
            config = Config("alembic.ini")
            config.attributes["connection"] = db
            command.check(config)
            command.downgrade(config, "0004_phase1c_gmail")
            assert db.scalar(text("SELECT to_regclass('expenses')")) is None
            command.upgrade(config, "head")
            command.check(config)
            assert db.scalar(text("SELECT version_num FROM alembic_version")) == "0005_phase2_meals"
            db.execute(
                text(
                    "INSERT INTO meal_policy_versions VALUES "
                    "('explicit-test-policy', '2026-01-01', "
                    "'ROUND_HALF_UP_LINE', '{}', now())"
                )
            )
        with pytest.raises(DBAPIError), engine.begin() as db:
            db.execute(text("UPDATE meal_policy_versions SET rounding='other'"))


@pytest.mark.parametrize("code", ["rate_limited", "model_timeout"])
def test_provider_transient_exhaustion_is_bounded_and_sanitized(client, postgres, meal, code):
    class Failure(FakeExtractor):
        def extract(self, *_):
            raise ExtractionFailure(code, True)

    for _ in range(3):
        with postgres[1].begin() as db:
            db.execute(ExpenseJob.__table__.update().values(available_at=datetime.now(UTC)))
        assert run(postgres, Failure())
    with postgres[1].connect() as db:
        assert db.scalar(select(ExpenseJob.attempts)) == 3
        assert db.scalar(select(ExpenseJob.state)) == "failed"
        assert db.scalar(select(ModelBudget.calls).where(ModelBudget.key == "global")) == 3


def test_fx_wrong_fallback_date_and_malformed_snapshot_are_pending(monkeypatch):
    from datetime import date

    adapter = HistoricalFx("synthetic")
    for payload in [
        {"timestamp": 1790899200, "base": "USD", "rates": {"EUR": "1", "GBP": ".8"}},
        {"timestamp": 1790985600, "base": "EUR", "rates": {"EUR": "1", "GBP": ".8"}},
        {"timestamp": 1790985600, "base": "USD", "rates": {"EUR": "0", "GBP": ".8"}},
    ]:

        def request(url, _, payload=payload):
            if "frankfurter" in url:
                raise FxPending("provider_unavailable")
            return payload

        monkeypatch.setattr(adapter, "request", request)
        with pytest.raises(FxPending):
            adapter.fetch("EUR", date(2026, 10, 3))


def test_fx_observation_boundary_rejects_wrong_date_pair_source_and_rate():
    from datetime import date

    from unloop.fx import validate_observation

    base = {
        "currency": "EUR",
        "date": "2026-10-01",
        "provider": "ecb",
        "source": "https://api.frankfurter.dev/v2/providers/ecb",
        "rate": ".85",
    }
    for update in [
        {"date": "2026-09-30"},
        {"currency": "USD"},
        {"source": "https://evil.invalid"},
        {"rate": "NaN"},
    ]:
        with pytest.raises(FxPending):
            validate_observation({**base, **update}, "EUR", date(2026, 10, 1))


def test_galileo_metadata_path_never_receives_receipts_conversations_or_credentials(monkeypatch):
    import galileo
    from unloop.extraction import _observe

    captured = {}

    class Logger:
        def __init__(self, **kwargs):
            pass

        def start_trace(self, **kwargs):
            captured.update(kwargs)

        def conclude(self, **kwargs):
            captured.update(kwargs)

        def flush(self, **kwargs):
            pass

    monkeypatch.setattr(galileo, "GalileoLogger", Logger)
    for key in ["GALILEO_API_KEY", "GALILEO_PROJECT", "GALILEO_LOG_STREAM"]:
        monkeypatch.setenv(key, "synthetic")
    assert (
        _observe(
            {
                "model": "gpt-6-luna",
                "outcome": "complete",
                "receipt": "private receipt",
                "conversation": "private words",
                "password": "private credential",
            }
        )
        == "sent"
    )
    assert "private" not in str(captured)
    assert set(captured["metadata"]) == {"model", "outcome"}


def test_model_configuration_cannot_infer_budget_from_key_presence():
    assert A1Settings.load({"OPENAI_API_KEY": "synthetic"}) is None
    with pytest.raises(ValueError):
        A1Settings.load({"A1_ENABLED": "true", "OPENAI_API_KEY": "synthetic"})
    assert "synthetic-not-a-live-key" not in repr(TEST_LIMITS)


def test_release_scorer_counts_missing_invalid_outputs_and_rejects_foreign_evidence():
    from scripts.meal_eval import score

    expected = SimpleNamespace(
        fields=SimpleNamespace(
            **{
                key: FACTS[key]
                for key in [
                    "merchant",
                    "receiptDate",
                    "originalAmount",
                    "transactionCurrency",
                    "mealType",
                ]
            }
        ),
        issue=None,
    )
    case = SimpleNamespace(
        id="synthetic",
        expected=expected,
        documents=[SimpleNamespace(documentId="document", pageCount=1)],
    )
    for records in [{}, {"synthetic": {"malformed": True}}]:
        result = score(records, [case])
        assert result["requiredFieldDenominator"] == 5
        assert result["readableDenominator"] == 1
        assert result["requiredFieldExact"] == result["readableReviewable"] == 0
    raw = output({"jobId": "job", "expenseRevisionId": "revision"}, {"id": "foreign"})
    assert score({"synthetic": raw}, [case])["schemaValid"] == 0


class PayloadExtractor(FakeExtractor):
    def __init__(self, change, facts=None):
        super().__init__(facts)
        self.change = change

    def extract(self, context, documents):
        raw, diagnostics = super().extract(context, documents)
        self.change(raw)
        return raw, diagnostics


class SpyFx:
    def __init__(self):
        self.calls = []

    def fetch(self, code, day):
        self.calls.append((code, day))
        return {
            "currency": code,
            "date": day.isoformat(),
            "provider": "ecb",
            "rate": "0.8",
            "source": "https://api.frankfurter.dev/v2/providers/ecb",
        }


@pytest.mark.parametrize(
    "state,readable,role,reason",
    [
        ("needsInformation", False, "receipt", None),
        ("needsInformation", True, "supportingDocument", None),
        ("couldNotRead", True, "receipt", None),
        ("needsInformation", True, "receipt", "multipleReceipts"),
    ],
)
def test_receipt_blockers_survive_recheck_and_checkbox_only_confirmation(
    client, postgres, meal, state, readable, role, reason
):
    _, headers, _, item = meal
    fx = SpyFx()

    def change(raw):
        raw["resultState"] = state
        raw["documentFindings"][0].update(readable=readable, apparentRole=role)
        if reason:
            raw["issues"] = [{"field": "receipt", "reason": reason, "evidenceRefs": []}]

    assert run(postgres, PayloadExtractor(change, {"transactionCurrency": "EUR"}), fx=fx)
    for action in ["recheck", "confirm"]:
        current = client.get(f"/api/expenses/{item['id']}").json()
        assert current["calculation"] is None and current["state"] != "review"
        assert current["provenance"]["receiptEligibility"]["eligible"] is False
        path = f"/api/expenses/{item['id']}" + ("/recheck" if action == "recheck" else "")
        command = {"version": current["version"]}
        if action == "confirm":
            command.update(facts=current["facts"], confirmed=True)
        response = (client.post if action == "recheck" else client.patch)(
            path, headers=headers, json=command
        )
        assert response.status_code == 200
        assert run(postgres, fx=fx)
    assert client.get(f"/api/expenses/{item['id']}").json()["calculation"] is None
    assert fx.calls == []
    # A fresh eligible receipt extraction, not a checkbox, may resolve the document decision.
    client.app.state.a1_settings = TEST_LIMITS
    current = client.get(f"/api/expenses/{item['id']}").json()
    assert (
        client.post(
            f"/api/expenses/{item['id']}/extract",
            headers=headers,
            json={"version": current["version"]},
        ).status_code
        == 200
    )
    assert run(postgres, FakeExtractor({"transactionCurrency": "EUR"}), fx=fx)
    assert client.get(f"/api/expenses/{item['id']}").json()["state"] == "review"
    assert len(fx.calls) == 1


@pytest.mark.parametrize(
    "vat_state,mixed", [("notFound", False), ("ambiguous", False), ("ambiguous", True)]
)
def test_optional_vat_is_blank_nonblocking_but_required_issues_remain(
    client, postgres, meal, vat_state, mixed
):
    _, _, _, item = meal

    def change(raw):
        raw["resultState"] = "needsInformation"
        raw["commonFields"]["vatAmount"]["state"] = vat_state
        raw["issues"] = [{"field": "vatAmount", "reason": "ambiguousEvidence", "evidenceRefs": []}]
        if mixed:
            raw["issues"].append(
                {"field": "originalAmount", "reason": "conflictingEvidence", "evidenceRefs": []}
            )

    fx = SpyFx()
    assert run(postgres, PayloadExtractor(change, {"transactionCurrency": "EUR"}), fx=fx)
    current = client.get(f"/api/expenses/{item['id']}").json()
    assert current["facts"]["vatAmount"] is None
    assert current["suggestion"]["diagnostics"]["optionalVat"] == "blank_nonblocking"
    assert current["state"] == ("needs_information" if mixed else "review")
    assert len(fx.calls) == (0 if mixed else 1)
    assert all(issue["field"] != "vatAmount" for issue in current["issues"])
    assert len(current["suggestion"]["output"]["issues"]) == (2 if mixed else 1)


def conflicting_pair(client, postgres, meal):
    _, headers, _, first = meal
    assert run(postgres)
    report, _ = report_and_headers(client)
    document = upload(
        client, report, headers, content=image_bytes("JPEG"), mime="image/jpeg", name="second.jpg"
    ).json()["documents"][0]["id"]
    assert run_once(postgres[1])
    second = client.post(
        f"/api/reports/{report}/expenses", headers=headers, json={"documentId": document}
    ).json()["expense"]
    assert run(postgres, FakeExtractor({"originalAmount": "20"}))
    return headers, first, second


@pytest.mark.parametrize(
    "field,value", [("receiptDate", "2026-10-02"), ("mealType", "lunch"), ("category", "air")]
)
def test_corrected_slot_restores_peer_without_model_or_fx_calls(
    client, postgres, meal, field, value
):
    headers, first, second = conflicting_pair(client, postgres, meal)
    fx = SpyFx()
    edit = client.patch(
        f"/api/expenses/{first['id']}",
        headers=headers,
        json={"version": 1, "facts": {field: value}, "confirmed": True},
    )
    assert edit.status_code == 200
    peer = client.get(f"/api/expenses/{second['id']}").json()
    assert peer["state"] == "review" and peer["calculation"]["claimGbp"] == "20.00"
    assert run(postgres, fx=fx)
    assert fx.calls == []
    with postgres[1].connect() as db:
        assert db.scalar(select(ModelBudget.calls).where(ModelBudget.key == "global")) == 2


def test_exclusion_restore_recomputes_two_report_conflicts_and_preserves_confirmation(
    client, postgres, meal
):
    headers, first, second = conflicting_pair(client, postgres, meal)
    response = client.patch(
        f"/api/expenses/{first['id']}", headers=headers, json={"version": 1, "excluded": True}
    )
    assert response.status_code == 200
    peer = client.get(f"/api/expenses/{second['id']}").json()
    assert peer["state"] == "review" and peer["calculation"]["claimGbp"] == "20.00"
    restored = client.patch(
        f"/api/expenses/{first['id']}", headers=headers, json={"version": 2, "excluded": False}
    )
    assert restored.status_code == 200
    assert client.get(f"/api/expenses/{second['id']}").json()["state"] == "conflict"
    assert run(postgres)
    assert client.get(f"/api/expenses/{first['id']}").json()["state"] == "conflict"


@pytest.mark.parametrize("invalid", ["single", "air", "excluded", "unreadable"])
def test_choose_rejects_ineligible_direct_calls_without_peer_writes(
    client, postgres, meal, invalid
):
    if invalid == "single":
        _, headers, _, first = meal
        assert run(postgres)
        peer = None
    else:
        headers, first, second = conflicting_pair(client, postgres, meal)
        if invalid == "air":
            assert (
                client.patch(
                    f"/api/expenses/{first['id']}",
                    headers=headers,
                    json={"version": 1, "facts": {"category": "air"}, "confirmed": True},
                ).status_code
                == 200
            )
            assert run(postgres)
        elif invalid == "excluded":
            assert (
                client.patch(
                    f"/api/expenses/{first['id']}",
                    headers=headers,
                    json={"version": 1, "excluded": True},
                ).status_code
                == 200
            )
        else:
            with postgres[1].begin() as db:
                db.execute(
                    Expense.__table__.update()
                    .where(Expense.id == first["id"])
                    .values(provenance={"receiptEligibility": {"eligible": False}})
                )
        peer = client.get(f"/api/expenses/{second['id']}").json()
    current = client.get(f"/api/expenses/{first['id']}").json()
    with postgres[1].connect() as db:
        count = db.scalar(select(func.count()).select_from(ExpenseJob))
    response = client.post(
        f"/api/expenses/{first['id']}/choose", headers=headers, json={"version": current["version"]}
    )
    assert response.status_code == 409
    if peer:
        assert client.get(f"/api/expenses/{second['id']}").json() == peer
    with postgres[1].connect() as db:
        assert db.scalar(select(func.count()).select_from(ExpenseJob)) == count


def test_arithmetic_reuse_has_active_revision_and_immutable_source_result(client, postgres, meal):
    from unloop.models import ExpenseCalculation, ExpenseRevision

    _, headers, _, item = meal
    assert run(postgres)
    before = client.get(f"/api/expenses/{item['id']}").json()
    after = client.patch(
        f"/api/expenses/{item['id']}",
        headers=headers,
        json={"version": 1, "facts": {"merchant": "Human corrected"}, "confirmed": True},
    ).json()
    assert after["calculation"]["expenseRevisionId"] == after["revisionId"]
    assert after["calculation"]["derivation"] == {
        "kind": "reused_arithmetic",
        "sourceRevisionId": before["revisionId"],
    }
    with postgres[1].connect() as db:
        rows = db.execute(select(ExpenseCalculation.revision_id, ExpenseCalculation.result)).all()
        assert len(rows) == 2
        snapshot = db.scalar(
            select(ExpenseRevision.snapshot).where(ExpenseRevision.id == after["revisionId"])
        )
        assert snapshot["calculation"] == after["calculation"]
        assert (
            next(row.result for row in rows if str(row.revision_id) == before["revisionId"])
            == before["calculation"]
        )


def test_legacy_ineligible_suggestion_cannot_expose_saved_claim_before_recheck(
    client, postgres, meal
):
    report, _, _, item = meal
    assert run(postgres)
    with postgres[1].begin() as db:
        db.execute(Expense.__table__.update().where(Expense.id == item["id"]).values(provenance={}))
        raw = db.scalar(select(ExtractionSuggestion.output))
        raw = {
            **raw,
            "resultState": "needsInformation",
            "documentFindings": [
                {**raw["documentFindings"][0], "apparentRole": "supportingDocument"}
            ],
        }
        db.execute(ExtractionSuggestion.__table__.update().values(output=raw))
    current = client.get(f"/api/expenses/{item['id']}").json()
    assert current["state"] == "needs_information" and current["calculation"] is None
    assert current["question"]["field"] == "receipt"
    assert client.get(f"/api/reports/{report}/expenses").json()["preparedClaimGbp"] == "0.00"
