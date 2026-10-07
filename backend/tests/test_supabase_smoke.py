"""Live-target guards plus real local HTTP smoke and failure cleanup."""

import json

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from scripts import supabase_smoke as smoke
from scripts.postgres_test_support import client_tls_in_use, isolated_database

POOLER = "aws-0-eu-west-2.pooler.supabase.com"
PROJECT = smoke.PROJECT_REF
VALID = f"postgresql://postgres.{PROJECT}:synthetic-password@{POOLER}:5432/postgres?sslmode=require"


@pytest.mark.parametrize(
    "url",
    [
        VALID,
        f"postgresql://postgres:synthetic-password@db.{PROJECT}.supabase.co:5432/postgres?sslmode=require",
        VALID.replace("sslmode=require", "sslmode=verify-full"),
        VALID.replace("sslmode=require", "sslmode=verify-ca"),
    ],
)
def test_live_target_accepts_only_expected_project_tls(url):
    normalized = make_url(smoke.validate_target(url))
    assert normalized.query["gssencmode"] == "disable"
    assert normalized.set(query=make_url(url).query) == make_url(url)


@pytest.mark.parametrize(
    "host, username",
    [
        (POOLER, f"postgres.{PROJECT}"),
        (f"db.{PROJECT}.supabase.co", "postgres"),
    ],
)
def test_missing_tls_mode_is_normalized_without_changing_login(host, username):
    raw = f"postgresql://{username}:synthetic%40password@{host}:5432/postgres"
    normalized = make_url(smoke.validate_target(raw))
    assert normalized.query == {"sslmode": "require", "gssencmode": "disable"}
    assert normalized.set(query={}) == make_url(raw)
    assert normalized.password == "synthetic@password"


@pytest.mark.parametrize(
    "url",
    [
        None,
        "invalid",
        VALID.replace(PROJECT, "anotherproject"),
        VALID.replace(POOLER, "attacker.example"),
        VALID.replace(":5432/", ":6543/"),
        VALID.replace("sslmode=require", "sslmode=prefer"),
        VALID.replace("sslmode=require", "sslmode=disable"),
        VALID.replace("sslmode=require", "sslmode=allow"),
        VALID + "&sslmode=require",
        VALID + "&host=attacker.example",
        VALID + "&hostaddr=127.0.0.1",
        VALID + "&options=-csearch_path=public",
        VALID + "&service=other",
        VALID + "&sslmode=disable",
        VALID.replace("/postgres?", "/other?"),
        VALID.replace(":synthetic-password@", "@"),
    ],
)
def test_live_target_fails_closed(url):
    with pytest.raises(smoke.SmokeFailure):
        smoke.validate_target(url)


@pytest.mark.parametrize("variable", ["CI", "GITHUB_ACTIONS"])
def test_local_cli_mode_is_forbidden_in_ci(monkeypatch, variable):
    monkeypatch.setenv(variable, "true")
    with pytest.raises(smoke.SmokeFailure) as error:
        smoke.validate_target(
            "postgresql://unloop@127.0.0.1:15433/unloop_smoke_test", local_test=True
        )
    assert error.value.code == "local_test_forbidden_in_ci"


def test_failure_output_does_not_include_url_or_exception(monkeypatch, capsys):
    monkeypatch.setenv("SUPABASE_SMOKE_DATABASE_URL", VALID)

    def fail(*args, **kwargs):
        raise RuntimeError("connection URL=" + VALID + " secret SQL and cookie")

    monkeypatch.setattr(smoke, "run_smoke", fail)
    assert smoke.main([]) == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {
        "status": "failed",
        "stage": "isolated_http_restart_smoke_or_cleanup",
        "code": "operation_failed",
    }
    assert not output.err and "synthetic-password" not in output.out


def schemas(engine):
    with engine.connect() as connection:
        return set(
            connection.scalars(
                text(
                    "SELECT schema_name FROM information_schema.schemata "
                    "WHERE schema_name LIKE 'unloop_test_%'"
                )
            )
        )


def test_real_local_http_smoke_and_restart(postgres):
    before = schemas(postgres[1])
    result = smoke.run_smoke(postgres[0], live=False)
    assert result["mode"] == "local_test_not_provider_evidence"
    assert result["http_restart_ownership_grade"] and result["schema_cleanup"]
    assert schemas(postgres[1]) == before


def test_real_local_assertion_failure_cleans_only_own_schema(postgres, monkeypatch):
    before = schemas(postgres[1])
    original = smoke.require

    def fail_at_proposal(condition, code):
        if code == "unconfirmed_report_persisted":
            raise smoke.SmokeFailure("injected_assertion_failure")
        original(condition, code)

    monkeypatch.setattr(smoke, "require", fail_at_proposal)
    with pytest.raises(smoke.SmokeFailure):
        smoke.run_smoke(postgres[0], live=False)
    assert schemas(postgres[1]) == before


def test_native_non_tls_connection_refused_before_schema_creation(postgres):
    with postgres[1].connect() as connection:
        tls = client_tls_in_use(connection)
    if tls:
        # On TLS-enabled ordinary CI PostgreSQL, success is also a valid engine check.
        with isolated_database(postgres[0], require_tls=True):
            pass
    else:
        before = schemas(postgres[1])
        with pytest.raises(RuntimeError, match="TLS connection required"):
            with isolated_database(postgres[0], require_tls=True):
                pytest.fail("Unencrypted connection was allowed")
        assert schemas(postgres[1]) == before


def test_ignored_search_path_cannot_migrate_default_schema(postgres, monkeypatch):
    from scripts import postgres_test_support as support

    before = schemas(postgres[1])
    original_engine = support.postgres_engine
    calls = 0
    migrated = False

    def ignore_scoped_options(url):
        nonlocal calls
        calls += 1
        # Simulate a session pooler ignoring the newly requested startup options;
        # both returned connections still use real PostgreSQL.
        return original_engine(url if calls == 1 else postgres[0])

    def migration_must_not_run(engine):
        nonlocal migrated
        migrated = True
        pytest.fail("Migration ran before isolated schema selection was established")

    monkeypatch.setattr(support, "postgres_engine", ignore_scoped_options)
    monkeypatch.setattr(support, "migrate", migration_must_not_run)
    with pytest.raises(RuntimeError, match="Isolated schema selection failed"):
        with support.isolated_database(postgres[0]):
            pytest.fail("Wrong schema was accepted")
    assert not migrated
    assert schemas(postgres[1]) == before


def test_actual_api_start_failure_discards_child_logs(capsys):
    import socket

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # Invalid driver makes the real child fail before any DB connection. Any
    # startup traceback stays in DEVNULL, rather than reaching the job output.
    with pytest.raises(smoke.SmokeFailure) as error:
        with smoke.api_process("unsupported://synthetic-secret@localhost/test", port):
            pytest.fail("API unexpectedly became ready")
    assert error.value.code == "api_start_failed"
    output = capsys.readouterr()
    assert not output.out and not output.err
