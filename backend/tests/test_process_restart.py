"""Real HTTP across two different API OS processes, using a disposable DB schema."""

import os
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx


@contextmanager
def api_process(database_url, port, *, schema):
    origin = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "unloop:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        env={
            **os.environ,
            "DATABASE_URL": database_url,
            "UNLOOP_TEST_SCHEMA": schema,
            "APP_ORIGIN": origin,
            "SESSION_COOKIE_SECURE": "false",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise AssertionError("Test API process failed to start")
            try:
                if httpx.get(origin + "/api/readiness", timeout=0.5).status_code == 200:
                    break
            except httpx.TransportError:
                pass
            time.sleep(0.05)
        else:
            raise AssertionError("Test API process did not become ready")
        yield origin
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_report_and_session_survive_an_actual_process_restart(app_config):
    with socket.socket() as socket_probe:
        socket_probe.bind(("127.0.0.1", 0))
        port = socket_probe.getsockname()[1]
    with (
        api_process(
            app_config["DATABASE_URL"], port, schema=app_config["UNLOOP_TEST_SCHEMA"]
        ) as origin,
        httpx.Client(base_url=origin) as client,
    ):
        started = client.post("/api/session", json={}, headers={"Origin": origin})
        assert started.status_code == 201
        headers = {"Origin": origin, "X-CSRF-Token": started.json()["csrfToken"]}
        proposed = client.post(
            "/api/report-proposals",
            json={
                "message": "Prepare my London report for 1–4 October 2026 for a client workshop."
            },
            headers=headers,
        ).json()
        result = client.post(
            "/api/reports",
            json={
                "proposalToken": proposed["proposalToken"],
                "confirmed": True,
                "header": proposed["header"],
            },
            headers=headers,
        )
        assert result.status_code == 201
        report = result.json()
        from backend.tests.test_evidence import image_bytes

        content = image_bytes()
        uploaded = client.post(
            f"/api/reports/{report['id']}/evidence",
            headers=headers,
            data={"source": "workspace"},
            files={"files": ("receipt.png", content, "image/png")},
        )
        assert uploaded.status_code == 201
        document_id = uploaded.json()["documents"][0]["id"]
        cookies = dict(client.cookies)
    with (
        api_process(
            app_config["DATABASE_URL"], port, schema=app_config["UNLOOP_TEST_SCHEMA"]
        ) as origin,
        httpx.Client(base_url=origin) as restarted,
    ):
        restarted.cookies.update(cookies)
        assert restarted.get("/api/session").json()["persona"] == "employee"
        assert restarted.get(f"/api/reports/{report['id']}").json() == report
        assert restarted.get("/api/reports").json()["reports"] == [report]
        assert restarted.get(f"/api/documents/{document_id}/original").content == content
        assert (
            restarted.get(f"/api/reports/{report['id']}/evidence").json()["documents"][0]["id"]
            == document_id
        )
