"""Diagnostic attribution/classification cannot emit driver secrets or arbitrary text."""

import errno
import json
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError

from scripts import supabase_smoke as smoke
from scripts.smoke_diagnostics import DiagnosticFailure, diagnostic_phase, safe_error_code

SECRET = "postgresql://postgres:synthetic-secret@db.example/postgres"


@pytest.mark.parametrize(
    "state, message, expected",
    [
        ("28P01", "password=" + SECRET, "auth_failed"),
        ("42501", SECRET, "permission_denied"),
        ("57014", SECRET, "query_timeout"),
        ("55P03", SECRET, "lock_timeout"),
        ("08006", SECRET, "connection_failed"),
        (None, "timeout expired " + SECRET, "connection_timeout"),
        (None, "Network is unreachable " + SECRET, "network_unreachable"),
        (None, "unsupported startup parameter: options " + SECRET, "unsupported_startup_parameter"),
        (None, "Tenant or user not found " + SECRET, "auth_failed"),
        (None, "unknown secret detail " + SECRET, "operation_failed"),
    ],
)
def test_driver_failure_maps_only_fixed_codes(state, message, expected):
    driver = RuntimeError(message)
    driver.sqlstate = state
    error = OperationalError("secret SQL " + SECRET, {"password": SECRET}, driver)
    assert safe_error_code(error) == expected


def test_nested_attribution_survives_successful_outer_cleanup(monkeypatch, capsys):
    uri = (
        f"postgresql://postgres.{smoke.PROJECT_REF}:synthetic-secret@"
        "aws-0-eu-west-1.pooler.supabase.com:5432/postgres"
    )
    monkeypatch.setenv("SUPABASE_SMOKE_DATABASE_URL", uri)

    def fail(*args, **kwargs):
        with diagnostic_phase("scoped_connection"):
            with diagnostic_phase("scoped_search_path"):
                raise RuntimeError("unsupported startup parameter " + uri)

    monkeypatch.setattr(smoke, "run_smoke", fail)
    assert smoke.main([]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "failed",
        "stage": "scoped_search_path",
        "code": "unsupported_startup_parameter",
    }
    assert not output.err and "synthetic-secret" not in output.out and uri not in output.out


@pytest.mark.parametrize(
    "stage",
    [
        "admin_connection",
        "admin_tls",
        "schema_creation",
        "scoped_connection",
        "scoped_search_path",
        "scoped_tls",
        "migration",
        "http_start",
        "http_restart",
        "schema_cleanup",
    ],
)
def test_stage_is_fixed_and_preserved(stage):
    with pytest.raises(DiagnosticFailure) as failure:
        with diagnostic_phase(stage):
            raise OSError(errno.ENETUNREACH, SECRET)
    assert failure.value.stage == stage and failure.value.code == "network_unreachable"
    assert str(failure.value) == ""


def test_ipv6_classification_is_bounded_and_does_not_rewrite_secret(monkeypatch, capsys):
    uri = f"postgresql://postgres:synthetic-secret@db.{smoke.PROJECT_REF}.supabase.co:5432/postgres"
    monkeypatch.setenv("SUPABASE_SMOKE_DATABASE_URL", uri)
    calls = []

    def probe(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"v6_only\n")

    def fail(*args, **kwargs):
        with diagnostic_phase("admin_connection"):
            raise TimeoutError(uri)

    monkeypatch.setattr(smoke.subprocess, "run", probe)
    monkeypatch.setattr(smoke, "run_smoke", fail)
    assert smoke.main([]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "ipv6_only_direct_target"
    assert not output.err and "synthetic-secret" not in output.out
    assert len(calls) == 1 and calls[0][1]["timeout"] == 3
    assert "synthetic-secret" not in repr(calls)
    assert smoke.direct_ipv6_only_after_failure(uri, "auth_failed", "admin_connection") is False
    assert len(calls) == 1
