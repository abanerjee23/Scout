"""Fixed diagnostic codes only; raw driver exceptions never leave this boundary."""

import errno
from contextlib import contextmanager

import httpx

STAGES = frozenset(
    {
        "admin_connection",
        "admin_tls",
        "schema_creation",
        "scoped_connection",
        "scoped_search_path",
        "scoped_tls",
        "migration",
        "migration_verification",
        "http_start",
        "http_flow",
        "http_restart",
        "schema_cleanup",
        "evidence_upload",
        "worker_recovery",
        "evidence_restart",
    }
)


class DiagnosticFailure(Exception):
    def __init__(self, code, stage=None):
        self.code, self.stage = code, stage
        super().__init__()


def safe_error_code(error):
    if getattr(error, "schema_code", None) == "isolated_schema_selection_failed":
        return "isolated_schema_selection_failed"
    tls_code = getattr(error, "tls_code", None)
    if tls_code in {
        "client_tls_not_active",
        "client_tls_state_missing",
        "client_tls_state_unknown",
        "client_tls_state_error",
    }:
        return tls_code
    driver = getattr(error, "orig", error)
    state = getattr(driver, "sqlstate", None) or getattr(driver, "pgcode", None)
    if isinstance(state, str):
        if state.startswith("28"):
            return "auth_failed"
        if state == "42501":
            return "permission_denied"
        if state == "57014":
            return "query_timeout"
        if state == "55P03":
            return "lock_timeout"
    if isinstance(error, httpx.TimeoutException):
        return "http_timeout"
    number = getattr(driver, "errno", None)
    if number in {errno.ENETUNREACH, errno.EHOSTUNREACH}:
        return "network_unreachable"
    if number == errno.ECONNREFUSED:
        return "connection_refused"
    if number == errno.ETIMEDOUT or isinstance(driver, TimeoutError):
        return "connection_timeout"
    # libpq/Supavisor transport failures often have no SQLSTATE. Inspect bounded
    # text internally; emit only these fixed labels, never the message itself.
    message = str(driver)[:8192].lower()
    for markers, code in (
        (
            ("unsupported startup parameter", "unrecognized configuration parameter"),
            "unsupported_startup_parameter",
        ),
        (("password authentication failed", "tenant or user not found"), "auth_failed"),
        (("timeout expired", "connection timed out"), "connection_timeout"),
        (("network is unreachable", "no route to host"), "network_unreachable"),
        (("could not translate host name", "name or service not known"), "name_resolution_failed"),
        (("connection refused",), "connection_refused"),
        (
            ("certificate verify failed", "server does not support ssl", "ssl error"),
            "tls_negotiation_failed",
        ),
    ):
        if any(marker in message for marker in markers):
            return code
    if isinstance(state, str) and state.startswith("08"):
        return "connection_failed"
    return "operation_failed"


@contextmanager
def diagnostic_phase(stage):
    if stage not in STAGES:
        raise ValueError("Unknown diagnostic stage")
    try:
        yield
    except DiagnosticFailure as error:
        if error.stage is None:
            error.stage = stage
        raise
    except Exception as error:
        raise DiagnosticFailure(safe_error_code(error), stage) from None
