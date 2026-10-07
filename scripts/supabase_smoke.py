"""Opt-in synthetic HTTP/restart smoke; never log connection URLs or exceptions."""

import argparse
import json
import logging
import os
import re
import signal
import socket
import subprocess
import sys
import time
from contextlib import contextmanager

import httpx
from sqlalchemy import text
from sqlalchemy.engine import make_url

from scripts.postgres_test_support import ROOT, client_tls_in_use, isolated_database
from scripts.smoke_diagnostics import DiagnosticFailure, diagnostic_phase, safe_error_code

PROJECT_REF = "lchwjzunjqtakjdnzrze"
REVISION = "0002_phase1a_hardening"


class SmokeFailure(DiagnosticFailure):
    """Only fixed, non-secret failure codes may be reported."""

    def __init__(self, code):
        super().__init__(code)


def require(condition, code):
    if not condition:
        raise SmokeFailure(code)


def validate_target(raw_url, *, local_test=False):
    require(bool(raw_url), "missing_connection_secret")
    try:
        url = make_url(raw_url)
        require(url.drivername in {"postgresql", "postgresql+psycopg"}, "postgresql_required")
        # libpq query parameters can override URL host/user/target. Allow only TLS mode.
        require(set(url.query) <= {"sslmode"}, "unsupported_connection_options")
        require(isinstance(url.query.get("sslmode", ""), str), "duplicate_tls_mode")
        if local_test:
            require(
                not os.environ.get("CI") and not os.environ.get("GITHUB_ACTIONS"),
                "local_test_forbidden_in_ci",
            )
            require(url.host in {"localhost", "127.0.0.1", "::1"}, "localhost_required")
            require(url.database == "unloop_smoke_test", "disposable_local_database_required")
        else:
            direct = url.host == f"db.{PROJECT_REF}.supabase.co" and url.username == "postgres"
            pooler = bool(re.fullmatch(r"[a-z0-9-]+\.pooler\.supabase\.com", url.host or ""))
            pooler = pooler and url.username == f"postgres.{PROJECT_REF}"
            require(direct or pooler, "project_target_mismatch")
            # Use direct/session pooling; transaction pooling cannot promise search_path state.
            require(url.port == 5432, "direct_or_session_port_required")
            require(url.database == "postgres" and bool(url.password), "database_login_required")
            if "sslmode" not in url.query:
                url = url.update_query_dict({"sslmode": "require"})
            require(
                url.query.get("sslmode") in {"require", "verify-ca", "verify-full"}, "tls_required"
            )
            url = url.update_query_dict({"gssencmode": "disable"})
    except SmokeFailure:
        raise
    except Exception:
        raise SmokeFailure("invalid_connection_configuration") from None
    return raw_url if local_test else url.render_as_string(hide_password=False)


@contextmanager
def api_process(database_url, port, *, schema=None):
    origin = f"http://127.0.0.1:{port}"
    # Do not forward the ambient environment/vault to the child. Its only DB URL
    # selects this invocation's schema; neither argv nor captured logs contain it.
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
            "critical",
            "--no-access-log",
        ],
        cwd=ROOT,
        env={
            "PATH": os.environ.get("PATH", ""),
            "DATABASE_URL": database_url,
            "UNLOOP_TEST_SCHEMA": schema or "",
            "APP_ORIGIN": origin,
            "SESSION_COOKIE_SECURE": "false",
        },
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 20
        with httpx.Client(base_url=origin, timeout=1, trust_env=False) as probe:
            while time.monotonic() < deadline:
                require(process.poll() is None, "api_start_failed")
                try:
                    response = probe.get("/api/readiness")
                    if response.status_code == 200:
                        require(
                            response.json().get("schemaVersion") == REVISION,
                            "api_revision_mismatch",
                        )
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise SmokeFailure("api_readiness_timeout")
        yield origin
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run_smoke(database_url, *, live):
    with isolated_database(database_url, require_tls=live, phase=diagnostic_phase) as (
        scoped_url,
        engine,
    ):
        with diagnostic_phase("migration_verification"), engine.connect() as connection:
            schema = connection.scalar(text("SELECT current_schema()"))
            require(
                bool(re.fullmatch(r"unloop_test_[0-9a-f]{32}", schema or "")),
                "isolated_schema_required",
            )
            tls = client_tls_in_use(connection)
            require(not live or tls is True, "connection_tls_not_active")
            require(
                connection.scalar(text("SELECT version_num FROM alembic_version")) == REVISION,
                "migration_revision_mismatch",
            )
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        with diagnostic_phase("http_start"), api_process(scoped_url, port, schema=schema) as origin:
            with (
                diagnostic_phase("http_flow"),
                httpx.Client(base_url=origin, timeout=10, trust_env=False) as client,
            ):
                started = client.post("/api/session", json={}, headers={"Origin": origin})
                require(started.status_code == 201, "session_start_failed")
                session = started.json()
                require(session["profile"].get("grade") == "C", "fixed_grade_failed")
                headers = {"Origin": origin, "X-CSRF-Token": session["csrfToken"]}
                require(
                    client.patch(
                        "/api/session/persona",
                        json={"persona": "employee", "grade": "G"},
                        headers=headers,
                    ).status_code
                    == 422,
                    "grade_edit_allowed",
                )
                proposed = client.post(
                    "/api/report-proposals",
                    headers=headers,
                    json={
                        "message": "Synthetic London report 1–4 October 2026 for a test workshop"
                    },
                )
                require(proposed.status_code == 200 and proposed.json()["ready"], "proposal_failed")
                proposal = proposed.json()
                payload = {
                    "proposalToken": proposal["proposalToken"],
                    "confirmed": True,
                    "header": proposal["header"],
                }
                with engine.connect() as connection:
                    require(
                        connection.scalar(text("SELECT count(*) FROM reports")) == 0,
                        "unconfirmed_report_persisted",
                    )
                    require(
                        connection.scalar(
                            text("SELECT grade FROM demo_profiles WHERE persona='employee'")
                        )
                        == "C",
                        "stored_grade_failed",
                    )
                require(
                    client.post(
                        "/api/reports", headers=headers, json={**payload, "confirmed": False}
                    ).status_code
                    == 422,
                    "implicit_confirmation_allowed",
                )
                with engine.connect() as connection:
                    require(
                        connection.scalar(text("SELECT count(*) FROM reports")) == 0,
                        "rejected_confirmation_persisted",
                    )
                result = client.post("/api/reports", json=payload, headers=headers)
                require(result.status_code == 201, "confirmation_failed")
                report = result.json()
                require(client.get("/api/reports").json() == {"reports": [report]}, "list_failed")
                require(
                    client.get(f"/api/reports/{report['id']}").json() == report, "refetch_failed"
                )
                cookies = dict(client.cookies)
        # First Uvicorn process has exited. Reuse its DB-owned cookie in another process.
        with (
            diagnostic_phase("http_restart"),
            api_process(scoped_url, port, schema=schema) as origin,
        ):
            with httpx.Client(
                base_url=origin, cookies=cookies, timeout=10, trust_env=False
            ) as client:
                require(
                    client.get("/api/session").json()["profile"].get("grade") == "C",
                    "restart_session_failed",
                )
                require(
                    client.get(f"/api/reports/{report['id']}").json() == report,
                    "restart_persistence_failed",
                )
                require(
                    client.get("/api/reports").json() == {"reports": [report]},
                    "restart_list_failed",
                )
                with httpx.Client(base_url=origin, timeout=10, trust_env=False) as other:
                    require(
                        other.post("/api/session", json={}, headers={"Origin": origin}).status_code
                        == 201,
                        "second_session_failed",
                    )
                    require(other.get("/api/reports").json() == {"reports": []}, "owner_list_leak")
                    require(
                        other.get(f"/api/reports/{report['id']}").status_code == 404,
                        "owner_read_leak",
                    )
                require(
                    client.patch(
                        "/api/session/persona", json={"persona": "manager"}, headers=headers
                    ).status_code
                    == 200,
                    "persona_switch_failed",
                )
                require(client.get("/api/reports").json() == {"reports": []}, "manager_list_leak")
                require(
                    client.get(f"/api/reports/{report['id']}").status_code == 403,
                    "manager_read_leak",
                )
                require(
                    client.post(
                        "/api/report-proposals",
                        headers=headers,
                        json={"message": "Synthetic report"},
                    ).status_code
                    == 403,
                    "manager_proposal_allowed",
                )
                require(
                    client.post("/api/reports", headers=headers, json=payload).status_code == 403,
                    "manager_confirmation_allowed",
                )
    # Success is emitted only after schema cleanup and both subprocesses exit.
    return {
        "mode": "live_supabase" if live else "local_test_not_provider_evidence",
        "project": PROJECT_REF if live else "localhost",
        "tls": bool(tls),
        "migration": REVISION,
        "http_restart_ownership_grade": True,
        "schema_cleanup": True,
    }


def direct_ipv6_only_after_failure(database_url, code, stage):
    if stage != "admin_connection" or code not in {
        "connection_timeout",
        "network_unreachable",
        "connection_refused",
        "connection_failed",
    }:
        return False
    host = f"db.{PROJECT_REF}.supabase.co"
    if make_url(database_url).host != host:
        return False
    try:
        # A bounded, credential-free DNS probe. Neither raw resolver errors nor
        # the connection URI reach this subprocess or the job output.
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import socket; a=socket.getaddrinfo('" + host + "',5432); "
                "f={x[0] for x in a}; "
                "print('v6_only' if socket.AF_INET6 in f and socket.AF_INET not in f else 'other')",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=3,
            check=False,
            env={"PATH": os.environ.get("PATH", "")},
        )
        return probe.returncode == 0 and probe.stdout.strip() == b"v6_only"
    except Exception:
        return False


def deadline(_signum, _frame):
    raise SmokeFailure("smoke_deadline")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--local-test",
        action="store_true",
        help="Local disposable engine test only; forbidden in CI/live mode",
    )
    args = parser.parse_args(argv)
    previous_logging = logging.root.manager.disable
    previous_alarm_handler = signal.getsignal(signal.SIGALRM)
    logging.disable(logging.CRITICAL)
    signal.signal(signal.SIGALRM, deadline)
    signal.alarm(180)
    stage = "target_validation"
    url = None
    try:
        variable = "TEST_DATABASE_URL" if args.local_test else "SUPABASE_SMOKE_DATABASE_URL"
        url = validate_target(os.environ.get(variable), local_test=args.local_test)
        stage = "isolated_http_restart_smoke_or_cleanup"
        result = run_smoke(url, live=not args.local_test)
        print(json.dumps({"status": "passed", **result}))
        return 0
    except BaseException as error:
        # No exception repr/traceback, URL, headers, cookie, SQL or subprocess logs.
        if isinstance(error, DiagnosticFailure):
            code, stage = error.code, error.stage or stage
        else:
            code = safe_error_code(error)
        if url and direct_ipv6_only_after_failure(url, code, stage):
            code = "ipv6_only_direct_target"
        print(json.dumps({"status": "failed", "stage": stage, "code": code}))
        return 1
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous_alarm_handler)
        logging.disable(previous_logging)


if __name__ == "__main__":
    sys.exit(main())
