# Local development and Cloud handoff

Updated: 8 October 2026 (Europe/London).

Unloop development now runs in `/Users/abhinavbanerjee/projects/vouch` on Abhinav's Mac. Use this checkout for coding, review and local validation; GitHub remains the source delivery and CI service, and Railway/Supabase remain separate deployment and integration gates. This change avoids repeated Cloud setup and Git-bundle transfers. Any improvement in iteration time still needs measurement.

## Migration and preservation

1. The Cloud implementation chat exported its final Phase 2 review fixes and stopped feature work. The existing **Finish Unloop build** Cloud follow-up is paused.
2. Snapshot `0281d0edabce44d45dcf729531d2d3ed1f5d782f` was imported from a checksum-verified Git bundle. The original is retained on `codex/phase-2-cloud-handoff` and `codex/phase-2`.
3. Active local branch `codex/local-end-to-end` was aligned onto the published Phase 1C commit `06444e700ba6beb706b74115659938780f2513c7`. The equivalent packaging cherry-pick was dropped; Cloud review fixes were retained.
4. The existing ignored `.env` and local PostgreSQL data were backed up under ignored `artifacts/local/local-migration/` before migrations. Existing `error.log` was retained. The initial local migration upgraded through `0005_phase2_meals`; subsequent category/policy/review migrations brought the database to `0008_phase5_review`, with metadata alignment verified.
5. Native macOS receipt validation was fixed: Darwin rejects the Linux address-space limit. Linux retains its 512 MiB cap; macOS retains the 10-second CPU limit, the parent's 15-second wall timeout and file/page/pixel limits. Native macOS does not provide the Linux memory cap. Use synthetic receipts for development; the Linux deployment boundary remains required for real-data readiness.

The build plan, held-out fixtures and separate hackathon repository were preserved. Cloud files, database contents and secrets were not treated as portable runtime state. Historical Cloud checks are in [the handoff record](../validation/PHASE_2_LOCAL_HANDOFF.md).

## Run locally

The existing `.env` already targets local PostgreSQL. Preserve it; use `.env.example` only when creating a missing configuration. Provider keys stay server-side and are not needed for report creation or manual evidence validation.

```sh
cd /Users/abhinavbanerjee/projects/vouch
uv sync --frozen
npm ci --prefix frontend
docker compose up -d --wait
uv run --frozen --env-file .env alembic upgrade head
```

Run each service in a separate terminal from the repository root:

```sh
# API
uv run --frozen --env-file .env uvicorn unloop:create_app --factory --host 127.0.0.1 --port 5001
```

```sh
# Evidence and expense worker
uv run --frozen --env-file .env python -m unloop.worker
```

```sh
# React workspace
npm run dev --prefix frontend
```

Open [the local workspace](http://127.0.0.1:5173). Use `127.0.0.1` consistently with `APP_ORIGIN`; an alternate hostname changes the origin. Stop each terminal with Ctrl+C. `docker compose stop` preserves data. Removing the volume discards local demo data.

Report creation, reopening and evidence validation work without model credentials. The owner-reviewed synthetic policy is active locally from 1 October 2026 with per-line ROUND_HALF_UP rounding and the reviewed Ground Transport rules. Paid extraction remains disabled pending credentials and budget. Browser Meal tests inject fake A1/FX adapters explicitly; their results are deterministic workflow evidence.

## Validate before continuing

Stop the development API/frontend/worker before browser tests. Ports 5001, 5002, 5173 and 5174 must be free. Run backend and browser suites sequentially and use two browser workers, matching the previously validated setup. Loading timeouts occurred with the default four workers; their cause remains unresolved.

```sh
uv run --frozen ruff check backend scripts
REQUIRE_POSTGRES_TESTS=true uv run --frozen --env-file .env pytest -q
uv run --frozen python -m unloop.fixture_check
uv run --frozen python -m unloop.worker --check
npm run build --prefix frontend
npx --prefix frontend playwright install chromium
REQUIRE_POSTGRES_TESTS=true uv run --frozen --env-file .env -- npm test --prefix frontend -- --workers=2
```

Tests use random isolated PostgreSQL schemas and real API/worker processes. A test skip is not persistence proof. Local fixture checks measure integrity, not model quality. Full local results belong in [the handoff validation record](../validation/PHASE_2_LOCAL_HANDOFF.md).

## Continue with live release validation

Phase 2 review findings were closed locally. Category fields, grounded policy assistance, explicit submitted snapshots, manager partial approval and the approved-release API now run on the active `codex/local-end-to-end` branch. Keep one active implementation chat; no manual worktree is required. Source delivery is consolidated through [PR #5](https://github.com/abanerjee23/UnLoop/pull/5) for `main`; the active local development branch is retained. Current readiness requires migration `0008_phase5_review`. A private `before-phase5.backup` was retained before upgrading the development database; metadata alignment passes. Submission history prevents downgrading 0008.

Phase 1C still needs hosted runtime/Gmail acceptance. Live model/FX evidence, measured release quality/latency/cost and paid budget remain pending. Policy review and local activation are complete. Abhinav selected Arize AI for evaluations and observability and GPT-6.1 Sol for the application on 8 October; the Arize AX integration is implemented locally, and the model migration is next in the [live backlog](BUILD_STATUS.md#live-pending-backlog). [Arize setup](../integrations/ARIZE.md) preserves frozen evals and privacy boundaries; live ingestion requires private credentials.

For each subsequent increment: record the user problem and acceptance criteria, implement a small demonstrable change locally, run relevant checks, review, then publish and inspect GitHub CI under the applicable delivery authorization. Measure time to a working preview and time to a validated increment to assess whether local development improves iteration speed.

Policy assistance uses the pinned pgvector PostgreSQL 17 image in `compose.yaml`, preserving the existing volume. A pre-change database dump is retained privately under `artifacts/local/local-migration/before-pgvector.backup`. Application migrations create only their own tables; they do not enable extensions or change shared provider schemas. For local policy retrieval, enable `vector` in a dedicated local extension schema once; production extension setup is a separate verified provider step. Portable embedding storage is evaluated using pgvector's exact cosine operator, with source/version/hash filters and mandatory rule passages. No approximate index is needed for this small policy.

A3 remains disabled until `POLICY_QA_ENABLED=true`, the approved policy and existing private A1 budget settings are configured. After approval, `uv run --frozen --env-file .env python -m unloop.policy_index` embeds only approved packaged clauses using `text-embedding-3-small`, 1536 dimensions; repeat runs reuse a complete matching index. Indexing, query embeddings and answers all consume the same persistent global reservation ceiling as receipt extraction. Test adapters are confined to test code and the disposable browser server.


Use `.env.example` for the complete private runtime field list without overwriting existing configuration. The current implementation still pins `gpt-6-luna`; the reviewed next model is `gpt-6.1-sol`. Update model-specific price floors and conservative reservations as part of that migration before configuring paid calls; recheck prices and account access. Reservations are guards, not measured spend. Actual embeddings, receipt extraction and policy answers use the same persistent ceiling. APPROVED_API_TOKEN is independent of the persona cookie; never put it in the frontend or shared request examples. Local policy approval flags are true following owner review; paid provider activation remains gated. [Selected model reference](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
