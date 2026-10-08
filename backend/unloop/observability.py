"""Bounded, content-free Arize AX traces; telemetry has no business authority."""

import json
import math
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from time import time_ns

REGIONS = {"us-central-1a", "us-east-1b", "eu-west-1a", "ca-central-1a"}
MODELS = {"gpt-6-luna", "gpt-6.1-sol", "text-embedding-3-small"}
PROMPTS = {"meal-a1-1", "meals-a1-1", "categories-a1-2", "policy-a3-1", "clauses-v1"}
SCHEMAS = {"0.1", "0.2", "policy-1", "embeddings-1"}
OUTCOMES = {
    "complete",
    "needsInformation",
    "couldNotRead",
    "unsupported",
    "answered",
    "notCovered",
    "needsClarification",
    "embedded",
    "model_timeout",
    "model_unavailable",
    "rate_limited",
    "invalid_output",
    "input_limit",
    "budget_exhausted",
    "model_unconfigured",
    "cost_unknown",
    "processing_failed",
    "answer_unavailable",
    "invalid_citations",
    "embedding_unavailable",
    "invalid_embedding",
    "question_input_limit",
    "question_unconfigured",
    "index_unavailable",
    "vector_unavailable",
    "stale_question",
    "guidance_unavailable",
}
OPERATIONS = {
    "extraction": "A1 receipt extraction",
    "policy": "A3 policy guidance",
    "embedding": "Policy embedding",
}


@dataclass(frozen=True, repr=False)
class ArizeSettings:
    key: str
    space: str
    project: str
    region: str

    @classmethod
    def load(cls, values, *, require_enabled=True):
        if require_enabled and values.get("ARIZE_ENABLED") != "true":
            return None
        if not all(
            values.get(key) for key in ["ARIZE_API_KEY", "ARIZE_SPACE_ID", "ARIZE_PROJECT_NAME"]
        ):
            return None
        result = cls(
            values["ARIZE_API_KEY"],
            values["ARIZE_SPACE_ID"],
            values["ARIZE_PROJECT_NAME"],
            values.get("ARIZE_REGION", "us-central-1a"),
        )
        if (
            result.region not in REGIONS
            or not re.fullmatch(r"[A-Za-z0-9_+/=-]{1,256}", result.space)
            or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", result.project)
            or not 1 <= len(result.key) <= 4096
            or any(character.isspace() for character in result.key)
        ):
            raise ValueError("Invalid private Arize configuration")
        return result

    @property
    def endpoint(self):
        return f"https://otlp.{self.region}.arize.com/v1/traces"


def safe_metadata(diagnostics):
    """Validate values as well as keys; untrusted strings cannot enter metadata slots."""
    if not isinstance(diagnostics, dict):
        return {}
    clean = {}
    for key, allowed in [
        ("model", MODELS),
        ("promptVersion", PROMPTS),
        ("schemaVersion", SCHEMAS),
        ("outcome", OUTCOMES),
    ]:
        value = diagnostics.get(key)
        if isinstance(value, str) and value in allowed:
            clean[key] = value
    for key in ["latencyMs", "inputTokens", "outputTokens"]:
        value = diagnostics.get(key)
        maximum = 600000 if key == "latencyMs" else 10000000
        if type(value) in (int, float) and 0 <= value <= maximum and math.isfinite(value):
            if key == "latencyMs" or type(value) is int:
                clean[key] = value
    value = diagnostics.get("estimatedCostUsd")
    if isinstance(value, str) and len(value) <= 40:
        try:
            amount = Decimal(value)
            if amount.is_finite() and 0 <= amount <= 10000:
                clean["estimatedCostUsd"] = str(amount)
        except InvalidOperation:
            pass
    if diagnostics.get("costBasis") == "configured_token_prices":
        clean["costBasis"] = "configured_token_prices"
    version = diagnostics.get("policyVersion")
    if isinstance(version, str) and re.fullmatch(
        r"synthetic-(?:te-0\.3|meals-0\.2):\d{4}-\d{2}-\d{2}", version
    ):
        clean["policyVersion"] = version
    mode = diagnostics.get("mode")
    if isinstance(mode, str) and mode in {"rag", "fullContext"}:
        clean["mode"] = mode
    return clean


def attributes(metadata, operation):
    from openinference.semconv.trace import OpenInferenceSpanKindValues, SpanAttributes

    result = {
        SpanAttributes.OPENINFERENCE_SPAN_KIND: (
            OpenInferenceSpanKindValues.EMBEDDING.value
            if operation == "embedding"
            else OpenInferenceSpanKindValues.LLM.value
        ),
        SpanAttributes.METADATA: json.dumps(metadata, sort_keys=True),
    }
    if "model" in metadata:
        key = (
            SpanAttributes.EMBEDDING_MODEL_NAME
            if operation == "embedding"
            else SpanAttributes.LLM_MODEL_NAME
        )
        result[key] = metadata["model"]
    if "inputTokens" in metadata:
        result[SpanAttributes.LLM_TOKEN_COUNT_PROMPT] = metadata["inputTokens"]
    if "outputTokens" in metadata:
        result[SpanAttributes.LLM_TOKEN_COUNT_COMPLETION] = metadata["outputTokens"]
    if "inputTokens" in metadata and "outputTokens" in metadata:
        result[SpanAttributes.LLM_TOKEN_COUNT_TOTAL] = (
            metadata["inputTokens"] + metadata["outputTokens"]
        )
    if "estimatedCostUsd" in metadata:
        result["unloop.estimated_cost_usd"] = float(metadata["estimatedCostUsd"])
    if "outcome" in metadata:
        result["unloop.outcome"] = metadata["outcome"]
    return result


def _observe(metadata, operation="extraction"):
    """Only runs in an isolated child in production; reports actual exporter acceptance."""
    # The exporter merges inherited OTEL headers even when explicit headers are passed.
    # This function runs only in the telemetry child; keep those ambient settings out.
    for key in list(os.environ):
        if key.startswith("OTEL_"):
            del os.environ[key]
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
    from opentelemetry.trace import Status, StatusCode

    settings = ArizeSettings.load(os.environ)
    if settings is None:
        return "unconfigured"
    if operation not in OPERATIONS:
        return "unavailable"

    class CheckedExporter(SpanExporter):
        result = SpanExportResult.FAILURE

        def __init__(self):
            self.delegate = OTLPSpanExporter(
                endpoint=settings.endpoint,
                timeout=1.5,
                headers={"arize-api-key": settings.key, "arize-space-id": settings.space},
            )

        def export(self, spans):
            self.result = self.delegate.export(spans)
            return self.result

        def shutdown(self):
            self.delegate.shutdown()

    exporter = CheckedExporter()
    # Resource() deliberately excludes inherited OTEL_RESOURCE_ATTRIBUTES and host/user identifiers.
    provider = TracerProvider(
        resource=Resource(
            {
                "service.name": "unloop-worker",
                "openinference.project.name": settings.project,
            }
        ),
        shutdown_on_exit=False,
    )
    try:
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        clean = safe_metadata(metadata)
        end = time_ns()
        start = end - int(clean.get("latencyMs", 0) * 1000000)
        span = provider.get_tracer("unloop").start_span(
            OPERATIONS[operation],
            attributes=attributes(clean, operation),
            start_time=start,
        )
        if clean.get("outcome") in OUTCOMES - {
            "complete",
            "needsInformation",
            "couldNotRead",
            "unsupported",
            "answered",
            "notCovered",
            "needsClarification",
            "embedded",
        }:
            span.set_status(Status(StatusCode.ERROR))
        span.end(end_time=end)
        return "sent" if exporter.result == SpanExportResult.SUCCESS else "unavailable"
    finally:
        provider.shutdown()


def _observation_child(metadata, operation, queue):
    import contextlib
    import logging

    with (
        open(os.devnull, "w") as sink,
        contextlib.redirect_stdout(sink),
        contextlib.redirect_stderr(sink),
    ):
        logging.disable(logging.CRITICAL)
        try:
            queue.put(_observe(metadata, operation))
        except Exception:
            queue.put("unavailable")


def _bounded_observe(diagnostics, *, operation="extraction"):
    """Three-second process deadline plus bounded termination; no business exceptions."""
    import multiprocessing

    if os.environ.get("ARIZE_ENABLED") != "true":
        return "disabled"
    try:
        if ArizeSettings.load(os.environ) is None:
            return "unconfigured"
        if operation not in OPERATIONS:
            return "unavailable"
        # Sanitize in the parent: receipt/private data never reaches the telemetry child.
        metadata = safe_metadata(diagnostics)
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        child = context.Process(
            target=_observation_child, args=(metadata, operation, queue), daemon=True
        )
        try:
            child.start()
            child.join(timeout=3)
            if child.is_alive():
                child.kill()
                child.join(timeout=1)
                return "timeout"
            try:
                state = queue.get(timeout=0.1)
                return state if state in {"sent", "unavailable", "unconfigured"} else "unavailable"
            except Exception:
                return "unavailable"
        finally:
            if child.is_alive():
                child.kill()
                child.join(timeout=1)
            queue.close()
    except Exception:
        return "unavailable"


def observe(diagnostics, *, operation="extraction"):
    state = _bounded_observe(diagnostics, operation=operation)
    if state in {"unavailable", "timeout", "unconfigured"}:
        import logging

        try:
            logging.getLogger(__name__).warning("Arize telemetry status: %s", state)
        except Exception:
            pass
    return state
