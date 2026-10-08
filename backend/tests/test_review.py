"""Submitted snapshots, partial releases and downstream boundaries on real PostgreSQL."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from unloop import create_app
from unloop.models import ApprovalRelease, ApprovedLine, ProcessingReady
from unloop.worker import run_once

from backend.tests.test_evidence import upload
from backend.tests.test_meals import TEST_POLICY, FakeExtractor, run
from backend.tests.test_meals import meal as meal

TOKEN = "synthetic-downstream-credential-at-least-32-characters"


def persona(client, headers, value):
    result = client.patch("/api/session/persona", headers=headers, json={"persona": value})
    assert result.status_code == 200


@pytest.fixture
def prepared(client, postgres, meal):
    client.app.state.meal_policy = TEST_POLICY
    client.app.state.approved_api_hash = hashlib.sha256(TOKEN.encode()).hexdigest()
    assert run(postgres)
    return meal


def preview(client, prepared):
    response = client.post(
        f"/api/reports/{prepared[0]}/submission-preview", headers=prepared[1], json={}
    )
    assert response.status_code == 200, response.text
    return response.json()


def submit(client, prepared, ids=None, **extra):
    value = preview(client, prepared)
    body = {
        "requestId": str(uuid4()),
        "previewToken": value["previewToken"],
        "expenseIds": ids or [line["expenseId"] for line in value["eligibleLines"]],
        "confirmed": True,
        **extra,
    }
    return client.post(
        f"/api/reports/{prepared[0]}/submissions", headers=prepared[1], json=body
    ), body


def release(client, prepared, lines, **extra):
    versions = {line["id"]: line["version"] for line in lines}
    response = client.post(
        "/api/review/release-preview", headers=prepared[1], json={"lineVersions": versions}
    )
    assert response.status_code == 200, response.text
    body = {
        "requestId": str(uuid4()),
        "previewToken": response.json()["previewToken"],
        "lineVersions": versions,
        "confirmed": True,
        **extra,
    }
    return client.post("/api/review/releases", headers=prepared[1], json=body), body


def manager_report(client):
    response = client.get("/api/review/reports")
    assert response.status_code == 200, response.text
    return response.json()["reports"][0]


def test_submit_preview_exact_snapshot_and_both_inboxes(client, postgres, prepared):
    value = preview(client, prepared)
    assert value["eligibleClaimGbp"] == "50.00"
    response, body = submit(client, prepared)
    assert response.status_code == 201, response.text
    snapshot = response.json()
    assert snapshot["lines"][0]["snapshot"]["facts"]["originalAmount"] == "62.00"
    assert (
        client.post(
            f"/api/reports/{prepared[0]}/submissions", headers=prepared[1], json=body
        ).json()["id"]
        == snapshot["id"]
    )
    assert client.get("/api/inbox").json()["events"][0]["payload"]["type"] == "submission_confirmed"
    persona(client, prepared[1], "manager")
    review = manager_report(client)
    assert review["pendingSubmittedClaimGbp"] == "50.00"
    assert client.get("/api/inbox").json()["events"][0]["payload"]["type"] == "review_requested"
    assert client.get(f"/api/expenses/{prepared[3]['id']}").status_code == 403


def test_material_edit_rejects_old_submission_without_disclosing_new_facts(
    client, postgres, prepared
):
    response, _ = submit(client, prepared)
    old = response.json()["lines"][0]
    assert (
        client.patch(
            f"/api/expenses/{prepared[3]['id']}",
            headers=prepared[1],
            json={
                "version": 1,
                "facts": {"merchant": "Private unsubmitted correction", "originalAmount": "45.00"},
                "confirmed": True,
            },
        ).status_code
        == 200
    )
    assert run(postgres)
    persona(client, prepared[1], "manager")
    review = manager_report(client)
    saved = review["submissions"][0]["lines"][0]
    assert saved["snapshot"]["facts"]["merchant"] == "Synthetic Kitchen"
    assert saved["needsResubmission"] is True
    assert "Private unsubmitted correction" not in str(review)
    assert (
        client.post(
            "/api/review/release-preview",
            headers=prepared[1],
            json={"lineVersions": {old["id"]: 1}},
        ).status_code
        == 409
    )


def test_stale_submission_preview_and_unconfirmed_commands_pause(client, postgres, prepared):
    value = preview(client, prepared)
    assert (
        client.patch(
            f"/api/expenses/{prepared[3]['id']}",
            headers=prepared[1],
            json={"version": 1, "facts": {"originalAmount": "45.00"}, "confirmed": True},
        ).status_code
        == 200
    )
    assert run(postgres)
    body = {
        "requestId": str(uuid4()),
        "previewToken": value["previewToken"],
        "expenseIds": [prepared[3]["id"]],
        "confirmed": True,
    }
    assert (
        client.post(
            f"/api/reports/{prepared[0]}/submissions", headers=prepared[1], json=body
        ).status_code
        == 409
    )
    body["confirmed"] = False
    assert (
        client.post(
            f"/api/reports/{prepared[0]}/submissions", headers=prepared[1], json=body
        ).status_code
        == 422
    )


def test_release_idempotency_immutable_facts_and_separate_downstream_credential(
    client, postgres, prepared
):
    response, _ = submit(client, prepared)
    persona(client, prepared[1], "manager")
    released, body = release(client, prepared, response.json()["lines"])
    assert released.status_code == 201, released.text
    data = released.json()
    assert data["approvedTotalGbp"] == "50.00"
    assert client.post("/api/review/releases", headers=prepared[1], json=body).json() == data
    assert client.get("/api/approved-releases").status_code == 401
    token = {"Authorization": "Bearer " + TOKEN}
    first = client.get("/api/approved-releases", headers=token).json()
    assert first == client.get("/api/approved-releases", headers=token).json()
    assert first["releases"] == [data]
    assert set(first["releases"][0]["lines"][0]) == {
        "expenseId",
        "approvedRevisionId",
        "merchant",
        "receiptDate",
        "category",
        "originalAmount",
        "originalCurrency",
        "fullGbpReceiptAmount",
        "approvedClaimGbp",
    }
    assert not any(
        word in str(first) for word in ["receiptDocumentId", "gmail", "policyVersion", "question"]
    )
    with Session(postgres[1]) as db:
        assert db.scalar(select(func.count()).select_from(ProcessingReady)) == 1
        assert db.scalar(select(func.count()).select_from(ApprovedLine)) == 1
    persona(client, prepared[1], "employee")
    assert client.get(f"/api/reports/{prepared[0]}").json()["status"] == "approved"
    for path, body, method in [
        (
            f"/api/expenses/{prepared[3]['id']}",
            {"version": 1, "facts": {"originalAmount": "1.00"}, "confirmed": True},
            "patch",
        ),
        (f"/api/expenses/{prepared[3]['id']}/extract", {"version": 1}, "post"),
        (f"/api/expenses/{prepared[3]['id']}/recheck", {"version": 1}, "post"),
    ]:
        result = getattr(client, method)(path, headers=prepared[1], json=body)
        assert result.status_code == 409
        assert result.json()["error"]["code"] == "approved_immutable"


def test_concurrent_release_same_request_creates_one_processing_record(client, postgres, prepared):
    response, _ = submit(client, prepared)
    persona(client, prepared[1], "manager")
    lines = response.json()["lines"]
    versions = {line["id"]: line["version"] for line in lines}
    value = client.post(
        "/api/review/release-preview", headers=prepared[1], json={"lineVersions": versions}
    ).json()
    body = {
        "requestId": str(uuid4()),
        "previewToken": value["previewToken"],
        "lineVersions": versions,
        "confirmed": True,
    }
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda _: client.post("/api/review/releases", headers=prepared[1], json=body),
                range(2),
            )
        )
    assert all(value.status_code == 201 for value in results), [value.text for value in results]
    assert results[0].json()["releaseId"] == results[1].json()["releaseId"]
    with Session(postgres[1]) as db:
        assert db.scalar(select(func.count()).select_from(ApprovalRelease)) == 1
        assert db.scalar(select(func.count()).select_from(ProcessingReady)) == 1


def test_return_requires_resubmission_and_question_does_not_reactivate_it(
    client, postgres, prepared
):
    response, _ = submit(client, prepared)
    line = response.json()["lines"][0]
    persona(client, prepared[1], "manager")
    result = client.post(
        f"/api/review/lines/{line['id']}/decisions",
        headers=prepared[1],
        json={
            "requestId": str(uuid4()),
            "version": 1,
            "action": "return",
            "message": "Please verify the amount.",
        },
    )
    assert result.status_code == 200
    result = client.post(
        f"/api/review/lines/{line['id']}/decisions",
        headers=prepared[1],
        json={
            "requestId": str(uuid4()),
            "version": 2,
            "action": "question",
            "message": "Which amount is on the receipt?",
        },
    )
    assert result.status_code == 200
    assert (
        client.post(
            "/api/review/release-preview",
            headers=prepared[1],
            json={"lineVersions": {line["id"]: 3}},
        ).status_code
        == 409
    )
    persona(client, prepared[1], "employee")
    question = client.get(f"/api/reports/{prepared[0]}/review-questions").json()["lines"][0][
        "questions"
    ][0]
    assert (
        client.post(
            f"/api/review-questions/{question['id']}/responses",
            headers=prepared[1],
            json={"version": 1, "response": "I checked the original; the amount is correct."},
        ).status_code
        == 200
    )
    response, _ = submit(client, prepared)
    assert response.status_code == 201
    persona(client, prepared[1], "manager")
    assert release(client, prepared, response.json()["lines"])[0].status_code == 201


def test_approved_meal_history_is_occupied_and_cannot_be_excluded_to_reclaim(
    client, postgres, prepared
):
    response, _ = submit(client, prepared)
    persona(client, prepared[1], "manager")
    assert release(client, prepared, response.json()["lines"])[0].status_code == 201
    persona(client, prepared[1], "employee")
    raw = BytesIO()
    Image.new("RGB", (8, 8), "red").save(raw, format="PNG")
    document = upload(client, prepared[0], prepared[1], content=raw.getvalue()).json()["documents"][
        0
    ]["id"]
    assert run_once(postgres[1])
    created = client.post(
        f"/api/reports/{prepared[0]}/expenses", headers=prepared[1], json={"documentId": document}
    ).json()["expense"]
    assert run(postgres)
    item = client.get(f"/api/expenses/{created['id']}").json()
    assert item["state"] == "conflict"
    assert (
        client.post(
            f"/api/expenses/{item['id']}/choose", headers=prepared[1], json={"version": 1}
        ).status_code
        == 409
    )
    assert client.get(f"/api/expenses/{prepared[3]['id']}").json()["state"] == "approved"
    assert (
        client.patch(
            f"/api/expenses/{prepared[3]['id']}",
            headers=prepared[1],
            json={"version": 1, "excluded": True},
        ).status_code
        == 409
    )


def test_database_rejects_mutation_of_submitted_payload_and_approved_releases(
    client, postgres, prepared
):
    response, _ = submit(client, prepared)
    persona(client, prepared[1], "manager")
    assert release(client, prepared, response.json()["lines"])[0].status_code == 201
    for sql in [
        "UPDATE approval_releases SET total_gbp='1.00'",
        "UPDATE approved_lines SET snapshot='{}'",
        "UPDATE submitted_lines SET snapshot='{}'",
        "DELETE FROM processing_ready",
    ]:
        with pytest.raises(DBAPIError), postgres[1].begin() as db:
            db.execute(text(sql))


def test_another_session_cannot_read_submitted_lines_or_receipts(client, app_config, prepared):
    response, _ = submit(client, prepared)
    line = response.json()["lines"][0]
    with TestClient(create_app(app_config), base_url="https://testserver") as other:
        started = other.post(
            "/api/session", headers={"Origin": "https://testserver"}, json={}
        ).json()
        headers = {"Origin": "https://testserver", "X-CSRF-Token": started["csrfToken"]}
        persona(other, headers, "manager")
        assert other.get("/api/review/reports").json()["reports"] == []
        assert other.get(f"/api/review/lines/{line['id']}/receipt").status_code == 404
        assert (
            other.post(
                "/api/review/release-preview",
                headers=headers,
                json={"lineVersions": {line["id"]: 1}},
            ).status_code
            == 404
        )


def test_ten_lines_release_nine_hold_correct_resubmit_and_separately_release_tenth(
    client, postgres, prepared
):
    ids = [prepared[3]["id"]]
    for index in range(1, 10):
        raw = BytesIO()
        Image.new("RGB", (8, 8), (index * 20, 40, 70)).save(raw, format="PNG")
        document = upload(client, prepared[0], prepared[1], content=raw.getvalue()).json()[
            "documents"
        ][0]["id"]
        assert run_once(postgres[1])
        item = client.post(
            f"/api/reports/{prepared[0]}/expenses",
            headers=prepared[1],
            json={"documentId": document},
        ).json()["expense"]
        assert run(
            postgres,
            FakeExtractor(
                {
                    "receiptDate": f"2026-10-0{index // 3 + 1}",
                    "mealType": ["dinner", "breakfast", "lunch"][index % 3],
                }
            ),
        )
        ids.append(item["id"])
    response, _ = submit(client, prepared)
    assert response.status_code == 201, response.text
    assert response.json()["claimGbp"] == "320.00"
    lines = response.json()["lines"]
    disputed = next(line for line in lines if line["expenseId"] == ids[-1])
    persona(client, prepared[1], "manager")
    assert (
        client.post(
            f"/api/review/lines/{disputed['id']}/decisions",
            headers=prepared[1],
            json={
                "requestId": str(uuid4()),
                "version": 1,
                "action": "question",
                "message": "Please check the total on this receipt.",
            },
        ).status_code
        == 200
    )
    first, _ = release(client, prepared, [line for line in lines if line["id"] != disputed["id"]])
    assert first.status_code == 201, first.text
    assert first.json()["approvedTotalGbp"] == "270.00"
    pending = manager_report(client)
    assert pending["approvedClaimGbp"] == "270.00"
    assert pending["pendingSubmittedClaimGbp"] == "50.00"
    persona(client, prepared[1], "employee")
    assert (
        client.patch(
            f"/api/expenses/{ids[-1]}",
            headers=prepared[1],
            json={"version": 1, "facts": {"originalAmount": "45.00"}, "confirmed": True},
        ).status_code
        == 200
    )
    assert run(postgres)
    second_submission, _ = submit(client, prepared, [ids[-1]])
    assert second_submission.status_code == 201, second_submission.text
    assert second_submission.json()["claimGbp"] == "45.00"
    persona(client, prepared[1], "manager")
    second, _ = release(client, prepared, second_submission.json()["lines"])
    assert second.status_code == 201, second.text
    assert second.json()["approvedTotalGbp"] == "45.00"
    assert first.json()["releaseId"] != second.json()["releaseId"]
    exported = client.get(
        "/api/approved-releases", headers={"Authorization": "Bearer " + TOKEN}
    ).json()["releases"]
    first_page = client.get(
        "/api/approved-releases?limit=1", headers={"Authorization": "Bearer " + TOKEN}
    ).json()
    assert first_page["releases"] == [first.json()]
    assert first_page["nextCursor"] == first.json()["releaseId"]
    second_page = client.get(
        "/api/approved-releases?limit=1&cursor=" + first_page["nextCursor"],
        headers={"Authorization": "Bearer " + TOKEN},
    ).json()
    assert second_page["releases"] == [second.json()] and second_page["nextCursor"] is None
    assert exported[0] == first.json()
    assert len(exported[0]["lines"]) == 9 and len(exported[1]["lines"]) == 1
    assert sum(Decimal(value["approvedTotalGbp"]) for value in exported) == Decimal("315.00")
    persona(client, prepared[1], "employee")
    assert client.get(f"/api/reports/{prepared[0]}").json()["status"] == "approved"


def test_concurrent_different_release_requests_approve_exactly_once(client, postgres, prepared):
    response, _ = submit(client, prepared)
    persona(client, prepared[1], "manager")
    versions = {line["id"]: line["version"] for line in response.json()["lines"]}
    token = client.post(
        "/api/review/release-preview", headers=prepared[1], json={"lineVersions": versions}
    ).json()["previewToken"]
    bodies = [
        {
            "requestId": str(uuid4()),
            "previewToken": token,
            "lineVersions": versions,
            "confirmed": True,
        }
        for _ in range(2)
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(
                lambda body: client.post("/api/review/releases", headers=prepared[1], json=body),
                bodies,
            )
        )
    assert sorted(value.status_code for value in results) == [201, 409]
    with Session(postgres[1]) as db:
        assert db.scalar(select(func.count()).select_from(ApprovalRelease)) == 1
        assert db.scalar(select(func.count()).select_from(ProcessingReady)) == 1


def test_pending_draft_is_not_disclosed_with_eligible_subset(client, postgres, prepared):
    raw = BytesIO()
    Image.new("RGB", (8, 8), "green").save(raw, format="PNG")
    document = upload(client, prepared[0], prepared[1], content=raw.getvalue()).json()["documents"][
        0
    ]["id"]
    assert run_once(postgres[1])
    hidden = client.post(
        f"/api/reports/{prepared[0]}/expenses", headers=prepared[1], json={"documentId": document}
    ).json()["expense"]
    value = preview(client, prepared)
    assert len(value["eligibleLines"]) == 1 and len(value["blockedLines"]) == 1
    response, _ = submit(client, prepared)
    assert response.status_code == 201
    assert response.json()["header"]["status"] == "submitted"
    persona(client, prepared[1], "manager")
    review = manager_report(client)
    assert hidden["id"] not in str(review) and document not in str(review)
    assert release(client, prepared, response.json()["lines"])[0].status_code == 201
    persona(client, prepared[1], "employee")
    assert client.get(f"/api/reports/{prepared[0]}").json()["status"] == "partially_approved"


def test_deactivated_policy_rejects_previously_signed_release(client, postgres, prepared):
    response, _ = submit(client, prepared)
    persona(client, prepared[1], "manager")
    versions = {line["id"]: line["version"] for line in response.json()["lines"]}
    token = client.post(
        "/api/review/release-preview", headers=prepared[1], json={"lineVersions": versions}
    ).json()["previewToken"]
    client.app.state.meal_policy = None
    result = client.post(
        "/api/review/releases",
        headers=prepared[1],
        json={
            "requestId": str(uuid4()),
            "previewToken": token,
            "lineVersions": versions,
            "confirmed": True,
        },
    )
    assert result.status_code == 409
    with Session(postgres[1]) as db:
        assert db.scalar(select(func.count()).select_from(ApprovalRelease)) == 0


def test_schema_downgrade_refuses_to_discard_submission_history(client, postgres, prepared):
    from alembic import command

    from backend.tests.test_hardening import migration_config

    response, _ = submit(client, prepared)
    assert response.status_code == 201
    with postgres[1].begin() as connection:
        config = migration_config(connection)
        with pytest.raises(RuntimeError, match="preserve immutable review history"):
            command.downgrade(config, "0007_phase4_policy")
    assert (
        client.get(f"/api/reports/{prepared[0]}/submissions").json()["submissions"][0]["id"]
        == response.json()["id"]
    )
