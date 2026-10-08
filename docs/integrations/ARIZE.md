# Arize AX evaluations and observability

Abhinav selected Arize AI on 8 October 2026. Unloop now uses Arize AX for runtime telemetry and synthetic evaluation experiments. The Galileo integration and dependencies are removed. Application facts, calculations and approvals remain code-owned. A1/A3 now pin `gpt-6.1-sol` with explicit medium reasoning; account ingestion and live provider measurements remain separate steps.

## Runtime traces

Set these fields privately on the worker when the credentials backlog item is reached:

```dotenv
ARIZE_ENABLED=true
ARIZE_API_KEY=<private server key>
ARIZE_SPACE_ID=<space ID>
ARIZE_PROJECT_NAME=unloop
ARIZE_REGION=us
```

Match the region to the account's Data Plane settings: `us` uses `https://otlp.arize.com/v1/traces` and the default US experiment API; `eu-west-1a` and `ca-central-1a` use their named regional hosts. The existing `us-central-1a` and `us-east-1b` settings remain supported for deployments that explicitly use those endpoints. Each setting selects a fixed HTTPS host. The example configuration defaults tracing to disabled; keys alone do not activate it. These US/EU/Canada hosts follow the [official region documentation](https://arize.com/docs/ax/security-and-settings/whitelisting).

A1 extraction, A3 policy answers and embedding calls emit manually constructed OpenInference spans. Validated attributes include model/prompt/schema/policy versions where available, outcome, timing, token counts and configured-price cost estimates when supplied. Embedding traces include usage but do not invent a cost estimate. Receipts, extracted merchant/amount facts, questions, conversations, identifiers, embeddings, credentials and exception bodies are omitted. Original OpenAI SDK tracing stays disabled.

Metadata keys and values are validated before entering the telemetry process. The child clears inherited OpenTelemetry settings so ambient resource attributes and merged headers cannot add private values. A fixed project/service resource avoids host and user identifiers. Runtime export has a three-second process deadline plus bounded termination, an explicit transport timeout, suppressed SDK output and no retry into financial operations. Rejected export returns unavailable rather than sent; fixed status warnings make missing configuration/export failure visible in worker logs. Collector acceptance still requires live verification in the selected Arize account.

This uses the documented [OpenTelemetry manual instrumentation](https://arize.com/docs/ax/instrument/manual-instrumentation) path and HTTP/protobuf with the transport-specific Arize headers.

## Evaluation experiments

`scripts/arize_eval.py` prepares experiments from the existing frozen synthetic Meal and policy result files. It reuses the local release scorers and does not call a model or judge. Policy rows preserve RAG/full-context pairs, exact citation validation, human correctness review and critical false-permission counts. Missing records and reviews stay visible as failures. Meal rows retain schema/field accuracy, critical financial errors and appropriate-pause scoring. The frozen thresholds and fixtures are unchanged.

Evaluation packets carry their score summary and explicitly state that supplied results are not live-model proof. Policy experiments can include validated synthetic answer text and questions for review; Meal experiments upload score rows without receipt contents or extraction payloads. No user correction, receipt or session collection is read. Held-out imports require `--release-heldout` and do not tune prompts or create new model inputs.

Prepare a private local packet from a synthetic result file:

```sh
uv run --frozen --env-file .env python -m scripts.arize_eval \
  --suite policy --results artifacts/local/policy-results.json \
  --output artifacts/local/arize-policy-preview.json
```

Explicitly upload that comparison after private credentials and the destination are configured:

```sh
uv run --frozen --env-file .env python -m scripts.arize_eval \
  --suite policy --results artifacts/local/policy-results.json \
  --upload --name unloop-policy-development-unique-run
```

Use `--suite meal` for Meal result maps. Uploads use the pinned Arize SDK experiment creation API with named evaluation columns and a 30-second process deadline. A failed or timed-out upload may have reached Arize; inspect the unique experiment name before retrying. No automatic re-upload or model execution occurs. The SDK interface is covered by an actual HTTP request/response test against a local server; it is not account ingestion evidence. See the official [Arize SDK experiments documentation](https://github.com/Arize-ai/client_python#create-an-experiment).

## Verification and remaining gates

Focused verification covers actual OTLP payloads and headers for all three operations, omission of private/inherited data, killed telemetry timeouts, exporter rejection, missing pairs/human review, critical false permission, held-out guards, private local previews and native SDK experiment payloads. These are engineering checks using local collectors and synthetic data.

Private Arize credentials, live dashboard ingestion, actual model results, held-out human review, measured quality/cost/latency and hosted runtime remain in their existing backlog steps. No Arize account, cloud project, external dataset or experiment was created during this migration.
