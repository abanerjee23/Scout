"""Parent-only synthetic live Meal gate. No keys, DB URI or direct provider calls.

Default only generates a synthetic PNG. --authorize-paid plus an exact deployed
origin is required to exercise server extraction, whose own budgets remain authoritative.
"""

import argparse
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageDraw, ImageFont


class GateFailure(Exception):
    pass


def receipt():
    image = Image.new("RGB", (900, 650), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("DejaVuSans.ttf", 30)
    for index, line in enumerate(
        [
            "SYNTHETIC TEST RECEIPT",
            "UnLoop Demo Kitchen",
            "DINNER",
            "Receipt date: 2026-10-01",
            "Food: GBP 55.00",
            "Service charge: GBP 7.00",
            "FINAL TOTAL: GBP 62.00",
            "VAT: not stated",
        ]
    ):
        draw.text((40, 40 + 65 * index), line, fill="black", font=font)
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return stream.getvalue()


def exercise(origin, content):
    stage = "session"
    try:
        with httpx.Client(base_url=origin, timeout=10, follow_redirects=False) as client:

            def post(path, body, headers):
                response = client.post(path, json=body, headers=headers)
                if response.status_code not in {200, 201}:
                    raise GateFailure()
                return response.json()

            started = post("/api/session", {}, {"Origin": origin})
            headers = {"Origin": origin, "X-CSRF-Token": started["csrfToken"]}
            stage = "report"
            proposal = post(
                "/api/report-proposals",
                {"message": "Synthetic London 1–4 October 2026 for a synthetic client workshop"},
                headers,
            )
            report = post(
                "/api/reports",
                {
                    "proposalToken": proposal["proposalToken"],
                    "header": proposal["header"],
                    "confirmed": True,
                },
                headers,
            )
            stage = "upload_validation"
            response = client.post(
                f"/api/reports/{report['id']}/evidence",
                headers=headers,
                data={"source": "workspace"},
                files={"files": ("synthetic-meal.png", content, "image/png")},
            )
            if response.status_code != 201:
                raise GateFailure()
            document = response.json()["documents"][0]["id"]
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                rows = client.get(f"/api/reports/{report['id']}/evidence").json()["documents"]
                if rows[0]["state"] == "validated":
                    break
                time.sleep(1)
            else:
                raise GateFailure()
            stage = "live_a1"
            expense = post(
                f"/api/reports/{report['id']}/expenses", {"documentId": document}, headers
            )["expense"]
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                saved = client.get(f"/api/expenses/{expense['id']}").json()
                if saved["state"] not in {"queued", "processing"}:
                    break
                time.sleep(1)
            else:
                raise GateFailure()
            if saved["state"] == "policy_inactive":
                stage = "owner_policy_inactive"
                raise GateFailure()
            if (
                saved["facts"]["originalAmount"] != "62.00"
                or saved["facts"]["transactionCurrency"] != "GBP"
                or saved["facts"]["receiptDate"] != "2026-10-01"
                or saved["facts"]["mealType"] != "dinner"
            ):
                raise GateFailure()
            stage = "saved_calculation"
            if saved["calculation"] is None or [
                saved["calculation"][key] for key in ["fullGbp", "claimGbp", "excessGbp"]
            ] != ["62.00", "50.00", "12.00"]:
                raise GateFailure()
            if client.get(f"/api/expenses/{expense['id']}").json() != saved:
                raise GateFailure()
            stage = "original_and_owner_isolation"
            raw = client.get(f"/api/documents/{document}/original").content
            if hashlib.sha256(raw).digest() != hashlib.sha256(content).digest():
                raise GateFailure()
            with httpx.Client(base_url=origin, timeout=10) as other:
                post_session = other.post("/api/session", json={}, headers={"Origin": origin})
                if (
                    post_session.status_code != 201
                    or other.get(f"/api/expenses/{expense['id']}").status_code != 404
                ):
                    raise GateFailure()
            client.patch("/api/session/persona", json={"persona": "manager"}, headers=headers)
            if client.get(f"/api/expenses/{expense['id']}").status_code != 403:
                raise GateFailure()
        return {
            "status": "passed",
            "synthetic": True,
            "saved_meal": True,
            "original_hash": True,
            "owner_manager_isolation": True,
            "deployment_restart": "not_measured",
            "foreign_fx": "not_measured",
            "quality_baseline": "not_measured",
        }
    except Exception:
        return {"status": "failed", "stage": stage, "code": "acceptance_failed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/local/phase2-synthetic.png"))
    parser.add_argument("--origin")
    parser.add_argument("--authorize-paid", action="store_true")
    args = parser.parse_args()
    content = receipt()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(content)
    if not args.authorize_paid:
        print(
            json.dumps(
                {
                    "status": "prepared_only",
                    "providerCalls": 0,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        )
        return
    parts = urlsplit(args.origin or "")
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.path
        or parts.username is not None
        or parts.query
        or parts.fragment
    ):
        parser.error("An exact reviewed HTTPS app origin is required")
    result = exercise(args.origin, content)
    print(json.dumps(result, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
