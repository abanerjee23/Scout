# Phase 1B — Retained evidence and recoverable validation jobs

> Dated validation record. Earlier implementation, approval, provider and PR statements below describe the recorded checkpoint. Present status: [current ledger and backlog](../product/BUILD_STATUS.md); latest checks: [Arize validation](ARIZE_LOCAL.md). Policy review/local activation and the Arize migration are complete; live release gates remain pending.

7 October 2026 (Europe/London). One Cloud implementation agent; branch `codex/phase-1b` from merged main `ac277d74496742deb584cdea16233b8ace0091a2` (PR #1). Full-version `abanerjee23/UnLoop`, no manual worktree. [Current delivery ledger](../product/BUILD_STATUS.md) carries standing authorization and next gates.

**Result: Phase 1B verified and review approved, ready for parent merge in [PR #2](https://github.com/abanerjee23/UnLoop/pull/2).** Verified 7 October 2026 at `599a391c009674d44dca9ad8275f4901ddb13031`: [hosted run 37673483432](https://github.com/abanerjee23/UnLoop/actions/runs/37673483432) passed **186 backend / 9 Chromium tests, zero skips**, and live Supabase job `112972061482` passed, including `evidence_bytes_dedup_restart_worker_recovery:true` and `schema_cleanup:true`. This proves synthetic isolated-schema provider persistence/restart/worker recovery; it does not prove Gmail, deployed UI/worker or production public migrations. Parent disabled `RUN_SUPABASE_SMOKE=false` after success. No AI/claims, submission or approval is included.

## Delivered boundaries

- Chat and workspace share `POST /api/reports/{id}/evidence` multipart ingestion. Only the persisted employee persona in the current session can upload/list/download/retry; origin and CSRF remain required on mutations. Report IDs and document IDs never confer cross-session access. Manager drafts/evidence are excluded.
- Candidate limits are 10 MiB/document, ten pages and ten files/batch, with a 101 MiB aggregate multipart envelope. Actual streaming bytes are counted independently of Content-Length. No partial DB writes if any file fails. Multipart temp files close on rejection.
- Actual signatures and MIME must match. Pillow verifies and decodes JPEG/PNG; animated/multipage images are rejected; 20 million pixels is the candidate bound. PDFs require valid page/content structure, one to ten positive-sized pages; encrypted or malformed PDFs are rejected. SHA256 hashes original bytes. Validation subprocesses enforce 15s wall, 10s CPU and 512 MiB address-space limits on Linux. These are engineering limits, not measured production budgets or proof of readable expense facts.
- `documents` contains metadata/state only; `document_bytes` retains originals separately. Owner/hash uniqueness deduplicates exact bytes within a session across reports; `evidence_links` preserves report/chat/workspace and safe filename provenance. Another owner receives a new ID and `duplicate=false`, regardless of matching bytes. Downloads are authorized attachments with nosniff/sandbox/no-store headers, not untrusted inline HTML.
- `evidence_jobs` commits before processing. Short `SKIP LOCKED` claim transactions assign a token and 30s lease; parsing runs outside locks. At most three attempts, transient-only backoff, expired-lease reclaim and token/expiry/current-revision guards protect idempotent state writes. Explicit failed-document retry creates a new revision/job while preserving bytes. There are no expense/inbox events to duplicate in this phase.
- UI polls metadata, clears evidence when switching report/persona, and presents empty/loading/error/upload/retry/queued/validating/validated/failed states on desktop/mobile. Queued evidence is retained even when the worker is stopped; validated means structural validation, never extracted/claim-ready. Start a real worker with `uv run --env-file .env python -m unloop.worker`, or `--once` for one due job. `--check` validates the entry point, not live worker health.
- Session expiry denies original access and prevents queued jobs from completing. Demo evidence remains in PostgreSQL until explicit database retention cleanup; automatic deletion/backup readiness remains separate before real-data use.

## Actual local evidence

Restored native PostgreSQL 17.11 on localhost port 15433, disposable `unloop_phase1b_test`, unique test schemas. Every shell activates `/workspace/.unloop-cloud/env.sh`; helper invoked through Bash. No provider TCP/credential access or global network policy changes.

| Command / gate | Actual result |
|---|---|
| `uv sync --frozen` | Pass |
| `uv run ruff check backend scripts` | Pass |
| `TEST_DATABASE_URL=… REQUIRE_POSTGRES_TESTS=true CI=true GITHUB_ACTIONS=true uv run --frozen pytest -q -ra` | **182 passed, zero skips**, one existing Starlette dependency warning |
| `uv run python -m unloop.fixture_check` | **24 cases**, 12/12 separation, **zero model runs** |
| `uv run python -m unloop.worker --check` | Pass; real queue execution proved separately by tests |
| `npm ci --prefix frontend` / `npm run build --prefix frontend` | Pass |
| `TEST_DATABASE_URL=… CI=true GITHUB_ACTIONS=true npm test --prefix frontend` | **9 passed, zero skips**; preserved seven and two new real API/PostgreSQL/worker evidence journeys |
| Migration 0003 | Fresh, 0002 upgrade, downgrade/re-upgrade, metadata alignment; existing report/session hardening/reopen regressions pass |
| Actual process recovery | Child OS process exits abruptly after committed claim; a new worker reclaims the expired lease and validates once, attempts=2 |
| Provider script in local tests | Real synthetic PNG/JPEG/PDF uploads, hashes, cross-report dedup, actual worker subprocess/expired-lease recovery, API process restart and owner/persona exclusion, cleanup all pass; explicitly **not provider evidence** |

The original 152 backend/seven browser tests remain included; narrow revision/table expectations were updated for the new migration. New tests cover malformed/truncated/MIME-spoofed/oversized/encrypted/over-page files, atomic batches, duplicate races, direct database owner foreign keys, original byte reopen/restart, concurrent worker claims, stale/expired leases, stale revisions, integrity failure, timeout retry and exhaustion. Injected timeout tests prove recovery logic only; real process/database tests establish persistence/recovery. Earlier full runs caught a stale Phase 1A table inventory and a multipart exception-boundary bug; both were fixed, then complete suites passed.

Fresh ignored screenshots `artifacts/local/phase1b-desktop.png` and `phase1b-mobile.png` were visually inspected: both upload controls remain available, lists/status/downloads readable, no horizontal overflow. Screenshots/test duration are not integration/product latency or savings proof. BUILD_PLAN, fixtures/held-out separation and archive remain unchanged; the separate hackathon repository is untouched. No prompt tuning or correction learning.

## Verified opt-in provider gate

The existing `Checks` job uses the private repository secret `SUPABASE_SMOKE_DATABASE_URL` only in its final live step. It requires the correct repository, **push**, exact **`refs/heads/codex/phase-1b`**, `RUN_SUPABASE_SMOKE=true` and successful backend/frontend jobs. PR/forks/ordinary checks cannot access it. The reviewed live run passed; the variable is now false again. A later skipped run is not new provider evidence. No new credential or secret re-entry is needed.

Parent reviewed and enabled the gate for the verified run above, then disabled it. `uv run --frozen python -m scripts.supabase_smoke` targets only project `lchwjzunjqtakjdnzrze`, requires client TLS with GSS disabled, creates a unique `unloop_test_<32hex>` schema, explicitly sets/verifies it on every connection and migrates the actual Alembic head. Synthetic PNG/JPEG/PDF upload and cross-report reuse, authorized hash/download/restart, worker subprocess terminal state/lease recovery and session/persona exclusions extend the original confirmation/grade checks. No public fallback or ALTER DATABASE/ROLE.

The 180s script/five-minute job bounds and fixed stage/code diagnostics remain; API/worker child logs are discarded. Success requires schema cleanup and `evidence_bytes_dedup_restart_worker_recovery=true`. The successful run above closes this increment's provider gate. Production public migrations, deployed UI/worker and later whole Phase 1 Gmail gates remain distinct.


### Lead-review follow-up — 7 October 2026

Upload authentication now uses a short unlocked read transaction before multipart intake, releases it before body receipt/validation, and acquires a fresh locking transaction only after the whole batch validates. Cookie/token, expiry, CSRF, employee persona and report ownership are checked again before dedup/bytes/links/jobs writes. Other Phase 1A routes retain their existing locking behavior. Multipart content-type errors now describe multipart intake correctly.

Delayed-validation regressions prove same-session reads and persona switching complete promptly; a persona switch or expiry during validation produces zero document/byte/link/job rows. Existing concurrent dedup tests remain. Targeted checks: four passed; full mandatory PostgreSQL suite with CI=true/GITHUB_ACTIONS=true: **186 passed, zero skips**; Chromium real API/PostgreSQL/worker suite: **9 passed, zero skips**; Ruff and diff whitespace checks passed. An initial test setup used the wrong persona route and violated the expiry ordering constraint; those test setup errors were corrected before the successful full run. Hosted/live follow-up passed at the exact commit/run recorded above; earlier failures are historical.
