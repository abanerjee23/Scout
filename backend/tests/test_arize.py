"""Real OTLP/SDK transport to local collectors; no account or paid model calls."""

import base64
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from unloop.meal_policy import MealPolicy
from unloop.observability import ArizeSettings, _observe, observe, safe_metadata
from unloop.policy_registry import registry

from scripts.arize_eval import prepare, publish
from scripts.policy_eval import load

CONFIG = {
    "ARIZE_ENABLED": "true",
    "ARIZE_API_KEY": "synthetic-key",
    "ARIZE_SPACE_ID": base64.b64encode(b"Space:synthetic").decode(),
    "ARIZE_PROJECT_NAME": "unloop-test",
    "ARIZE_REGION": "eu-west-1a",
}
POLICY = MealPolicy.load(
    {
        "MEAL_POLICY_APPROVED": "true",
        "MEAL_POLICY_EFFECTIVE_DATE": "2026-10-01",
        "MEAL_POLICY_ROUNDING": "ROUND_HALF_UP_LINE",
        "GROUND_POLICY_APPROVED": "true",
    }
)


@contextmanager
def collector():
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_POST(self):
            requests.append(
                (
                    self.path,
                    dict(self.headers),
                    self.rfile.read(int(self.headers["Content-Length"])),
                )
            )
            self.send_response(201 if self.path == "/v2/experiments" else 200)
            self.send_header(
                "Content-Type",
                "application/json" if self.path == "/v2/experiments" else "application/x-protobuf",
            )
            self.end_headers()
            if self.path == "/v2/experiments":
                self.wfile.write(
                    json.dumps(
                        {
                            "id": "synthetic-experiment",
                            "name": "unloop-synthetic",
                            "space_id": CONFIG["ARIZE_SPACE_ID"],
                            "created_at": "2026-10-08T12:00:00Z",
                            "updated_at": "2026-10-08T12:00:00Z",
                        }
                    ).encode()
                )

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def configure(monkeypatch):
    for key, value in CONFIG.items():
        monkeypatch.setenv(key, value)


def spawned_test_child(metadata, operation, queue):
    # This test target is importable by spawn; production has no custom endpoint setting.
    from unloop.observability import _observation_child

    ArizeSettings.endpoint = property(lambda _self: os.environ["UNLOOP_TEST_COLLECTOR"])
    _observation_child(metadata, operation, queue)


def test_real_spawned_export_process_reports_acceptance_without_private_metadata(monkeypatch):
    import unloop.observability as telemetry

    configure(monkeypatch)
    with collector() as (server, requests):
        monkeypatch.setenv(
            "UNLOOP_TEST_COLLECTOR", f"http://127.0.0.1:{server.server_port}/v1/traces"
        )
        monkeypatch.setattr(telemetry, "_observation_child", spawned_test_child)
        assert (
            observe({"model": "gpt-6.1-sol", "outcome": "complete", "receipt": "private"}) == "sent"
        )
        assert len(requests) == 1 and b"private" not in requests[0][2]


def test_credential_presence_alone_never_activates_traces(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("ARIZE_ENABLED", "false")
    assert observe({"receipt": "private"}) == "disabled"
    monkeypatch.setenv("ARIZE_ENABLED", "true")
    monkeypatch.delenv("ARIZE_API_KEY")
    assert observe({}) == "unconfigured"
    assert "synthetic-key" not in repr(ArizeSettings.load(CONFIG))


def test_metadata_slots_reject_injected_private_strings_and_invalid_numbers():
    assert (
        safe_metadata(
            {
                "model": "private receipt",
                "promptVersion": "private conversation",
                "schemaVersion": "private password",
                "outcome": "private token",
                "latencyMs": True,
                "inputTokens": -1,
                "outputTokens": float("inf"),
                "estimatedCostUsd": "NaN",
                "costBasis": "private",
                "policyVersion": "private",
                "mode": ["private"],
                "receipt": "private",
            }
        )
        == {}
    )


@pytest.mark.parametrize("operation", ["extraction", "policy", "embedding"])
def test_actual_otlp_payload_omits_all_private_content_and_inherited_resources(
    monkeypatch, operation
):
    from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import ExportTraceServiceRequest

    configure(monkeypatch)
    monkeypatch.setenv("OTEL_RESOURCE_ATTRIBUTES", "user.id=private-user,password=private-password")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_HEADERS", "private=private-secret")
    with collector() as (server, requests):
        # Test-only endpoint; deployed configuration uses fixed Arize region hosts.
        monkeypatch.setattr(
            ArizeSettings,
            "endpoint",
            property(lambda _self: f"http://127.0.0.1:{server.server_port}/v1/traces"),
        )
        assert (
            _observe(
                {
                    "model": (
                        "text-embedding-3-small" if operation == "embedding" else "gpt-6.1-sol"
                    ),
                    "outcome": "embedded" if operation == "embedding" else "complete",
                    "latencyMs": 15,
                    "inputTokens": 100,
                    "outputTokens": 10,
                    "estimatedCostUsd": "0.00002",
                    "costBasis": "configured_token_prices",
                    "receipt": "private receipt",
                    "conversation": "private words",
                    "password": "private credential",
                },
                operation,
            )
            == "sent"
        )
        assert len(requests) == 1
        path, headers, raw = requests[0]
        headers = {key.lower(): value for key, value in headers.items()}
        assert path == "/v1/traces" and headers["arize-api-key"] == CONFIG["ARIZE_API_KEY"]
        assert headers["arize-space-id"] == CONFIG["ARIZE_SPACE_ID"]
        assert "private" not in str(headers).lower() and b"private" not in raw
        decoded = ExportTraceServiceRequest.FromString(raw)
        resources = decoded.resource_spans[0]
        assert {value.key for value in resources.resource.attributes} == {
            "service.name",
            "openinference.project.name",
        }
        span = resources.scope_spans[0].spans[0]
        attrs = {value.key: value.value for value in span.attributes}
        assert attrs["llm.token_count.total"].int_value == 110
        assert span.end_time_unix_nano - span.start_time_unix_nano == 15000000
        assert not span.events


def test_timeout_kills_child_and_only_sanitized_metadata_crosses_boundary(monkeypatch):
    import multiprocessing

    configure(monkeypatch)
    captured = {}

    class Child:
        alive = True

        def __init__(self, **kwargs):
            captured.update(kwargs)

        def start(self):
            pass

        def join(self, timeout):
            captured.setdefault("joins", []).append(timeout)

        def is_alive(self):
            return self.alive

        def kill(self):
            self.alive = False
            captured["killed"] = True

    queue = SimpleNamespace(close=lambda: None)
    monkeypatch.setattr(
        multiprocessing,
        "get_context",
        lambda _method: SimpleNamespace(Queue=lambda: queue, Process=Child),
    )
    assert observe({"model": "gpt-6.1-sol", "receipt": "private"}) == "timeout"
    assert captured["args"][0] == {"model": "gpt-6.1-sol"}
    assert captured["joins"] == [3, 1] and captured["killed"]
    monkeypatch.setenv("ARIZE_REGION", "private-invalid-region")
    assert observe({}) == "unavailable"


def test_exporter_rejection_is_not_reported_as_sent(monkeypatch):
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace.export import SpanExportResult

    configure(monkeypatch)
    monkeypatch.setattr(OTLPSpanExporter, "export", lambda _self, _spans: SpanExportResult.FAILURE)
    assert _observe({"model": "gpt-6.1-sol", "outcome": "model_timeout"}) == "unavailable"


def test_missing_pairs_and_reviews_remain_visible_failed_experiment_rows():
    packet = prepare("policy", [], policy=POLICY)
    assert len(packet["runs"]) == 24
    assert not packet["summary"]["qualityGatePassed"]
    assert all(
        row["humanReviewed"] == 0 and row["output"]["state"] == "missing" for row in packet["runs"]
    )
    with pytest.raises(ValueError):
        prepare("policy", [], policy=POLICY, split="heldout")
    meal = prepare("meal", {})
    assert not meal["summary"]["qualityGatePassed"]
    assert len(meal["runs"]) == 12


def test_citation_and_human_false_permission_failures_keep_original_scorer_semantics():
    case = load("development")[1]
    source = registry(POLICY)
    record = {
        "caseId": case["id"],
        "mode": "rag",
        "policyVersion": source["version"],
        "humanReview": {"fullyCorrect": True, "falsePermission": True},
        "diagnostics": {
            "receipt": "private",
            "model": "gpt-6.1-sol",
            "policyVersion": "synthetic-meals-0.2:2026-01-01",
            "mode": "fullContext",
        },
        "result": {
            "state": "answered",
            "answer": "Synthetic incorrect permission.",
            "citations": [
                {
                    "clauseId": id,
                    "quote": next(c["text"] for c in source["clauses"] if c["id"] == id)[:80],
                }
                for id in case["expectedClauseIds"]
            ],
        },
    }
    packet = prepare("policy", [record], policy=POLICY)
    row = next(
        value
        for value in packet["runs"]
        if value["caseId"] == case["id"] and value["mode"] == "rag"
    )
    assert row["fullyCorrect"] == 0 and row["criticalFalsePermission"] == 1
    assert row["policyVersion"] == source["version"] and "private" not in json.dumps(packet)
    assert packet["providerCalls"] == 0 and packet["isLiveModelProof"] is False


def test_real_arize_sdk_posts_scores_to_local_experiment_endpoint():
    from arize import ArizeClient

    packet = prepare("policy", [], policy=POLICY)
    with collector() as (server, requests):
        client = ArizeClient(
            api_key="synthetic-key",
            api_host="127.0.0.1",
            api_scheme="http",
            api_port=server.server_port,
            enable_caching=False,
        )
        result = publish(packet, "unloop-synthetic", ArizeSettings.load(CONFIG), client=client)
        assert result.id == "synthetic-experiment"
        assert len(requests) == 1 and requests[0][0] == "/v2/experiments"
        body = json.loads(requests[0][2])
        assert len(body["experiment_runs"]) == 24
        row = body["experiment_runs"][0]
        assert row["eval.fullyCorrect.score"] == 0
        assert row["eval.humanReviewed.score"] == 0


def test_default_cli_writes_private_local_preview_without_credentials(tmp_path):
    records, output = tmp_path / "records.json", tmp_path / "preview.json"
    records.write_text("{}")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.arize_eval",
            "--suite",
            "meal",
            "--results",
            str(records),
            "--output",
            str(output),
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == 0
    summary = json.loads(result.stdout)
    assert summary["status"] == "local_preview" and summary["providerCalls"] == 0
    assert output.stat().st_mode & 0o777 == 0o600
    assert json.loads(output.read_text())["summary"]["qualityGatePassed"] is False
