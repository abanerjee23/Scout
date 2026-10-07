# Phase 1A — Implementation and validation

Date: 7 October 2026 (Europe/London).

Scope: server-owned demo sessions/personas, deterministic Astra report proposal/review/confirmation, PostgreSQL-backed report list/read/reopen. Backend is **FastAPI/Python**, explicitly requested by the user after the audit. One implementation agent, branch `codex/phase-1a`, no manual worktree.

**Result: Phase 1A implementation, local PostgreSQL gates and hosted GitHub CI pass. Supabase PostgreSQL connectivity remains unverified; full provider-specific Phase 1A sign-off is PARTIAL.** Phases 1B/1C and later are not started by this increment. Cloud environment/review setup is a separate gate.

Starting baseline: `5fa19ba` (tested Phase 0 source and audit, established locally). The prior audit remains a dated pre-implementation matrix. The build plan, A1 schema, fixture checker, development/held-out fixtures and archive originals are unchanged. Flask was replaced by FastAPI per the user's direct instruction; its health capability and existing contract/fixture/preview checks are retained with the API test harness adapted.

## Actual architecture

- `backend/unloop/__init__.py`: FastAPI factory, sanitized errors, mutation origin/JSON/body boundary and no-store responses. No automatic schema writes on startup.
- `database.py`, `models.py`: PostgreSQL-only SQLAlchemy, session/profile/report entities.
- `api.py`: authorized session/persona/proposal/confirmation/list/read routes; health/readiness separate.
- `intake.py`: strict Pydantic input validation and deterministic bounded parsing; no model call.
- `backend/migrations/versions/0001_phase1a.py`: actual Alembic migration; no future evidence/jobs/Gmail/approval tables.
- `frontend/src/components/`: Astra intake, private report list, saved report workspace. Invalid/expired session and stale persona failures clear private UI state. URL selection is re-authorized by the API.
- `frontend/src/SyntheticPreview.tsx`: labelled expected-value preview at `/?preview=1`, separate from persisted reports.

## Acceptance evidence matrix

| Requirement | Local status | Actual evidence |
|---|---|---|
| Opaque httpOnly secure cookie and expiry | Pass | `test_session_cookie_and_seeded_profiles`: random 43-character cookie, HttpOnly/Secure/SameSite=Lax/Max-Age/Expires, only SHA256 bearer hash in DB, default eight-hour fixed expiry. |
| Missing/fabricated/expired sessions fail closed | Pass | `test_missing_invalid_and_expired_sessions`, `test_valid_length_fabricated_cookie_is_rejected`; invalid/expired cookies cleared, no report persisted. |
| Predefined personas, fixed server-seeded grade | Pass | DB/API tests assert employee C/manager no grade; strict mutation schemas reject grade/identity injection. Profile constraint also fixes employee grade. |
| Origin and CSRF for state changes | Pass | Bootstrap cross-site tests; all mutation-origin/CSRF tests including report confirmation and another session's token. Bootstrap requires exact origin/JSON; subsequent writes also require per-session CSRF. |
| Session ownership | Pass | `test_isolation_and_proposal_cannot_cross_sessions`; real second-browser-context test; foreign report IDs give 404, foreign proposal/CSRF fail. |
| Manager cannot read/create drafts | Pass | `test_manager_visibility_and_client_persona_spoofing`; real browser toggle/direct GET/refresh; manager list is empty without querying draft rows. Spoofed persona/grade headers confer no authority. |
| Stale employee UI cannot bypass server persona | Pass | Real browser test changes server persona independently, attempts confirmation from stale form, gets refusal and clears/refetches authoritative persona. |
| Natural report description proposes editable structured header | Pass | Explicit ISO/English single-day/same-month/cross-month parser tests, real browser proposed fields and edited report name. |
| Explicit year, chronology and business purpose validation | Pass | Missing-year, ambiguous dates, invalid/leap dates, incomplete ranges and relative dates pause; invalid confirmed dates/purpose/name/extra fields return 422 and create no report. |
| No report before explicit confirmation | Pass | `test_proposal_is_not_a_report_then_confirmation_persists`: DB/API count remains zero; false/string/number/null confirmation rejected. Browser verifies empty list before save. |
| No manager details requested or persisted | Pass | Strict input schemas reject `managerEmail`; inspection confirms no manager fields in report table; browser has no manager-email field; parser does not request one. |
| Confirmation retry/concurrency | Pass | Same proposal/header returns identical ID; different payload after confirmation returns 409; simultaneous confirmations produce one row (201 + 200). Owner row lock and DB unique owner/confirmation pair. |
| Proposed values are not write authority | Pass | Proposal is signed/session-bound, expires after 20 minutes; explicit confirmation validates header again in code. Forged/foreign/expired proposals rejected. No models or tools invoked. |
| Save/list/read/reopen/reload | Pass | Actual PostgreSQL API tests and browser reload/corrected header/reopen; selected ID fetched through authorized endpoint. No authoritative localStorage/in-memory substitute. |
| Persistence after actual API process restart | Pass | `test_process_restart.py`: real HTTP, saves report, stops first Uvicorn OS process, starts second process on same migrated test schema, reuses valid cookie and reopens exact saved report. |
| Migration and metadata | Pass | Fresh random PostgreSQL schema migrated with Alembic; repeated upgrade and `alembic check` show alignment; only sessions/profiles/reports plus Alembic table. |
| Empty/loading/error and narrow-screen states | Pass | Real browser creation/mobile correction/no-overflow; invalid session requires explicit new session; error/manager-empty UI; desktop/mobile screenshots inspected. |
| Supabase PostgreSQL migration/create/reopen | **UNVERIFIED** | No Supabase `DATABASE_URL` was configured. Disposable local PostgreSQL is real persistence evidence, not provider connectivity proof. |
| Published commit's GitHub Actions | **PASS** | Baseline `5fa19ba` passed. The first Phase 1A run exposed a Linux `scripts` import failure; `8484701` explicitly sets pytest's root Python path. Its backend/frontend jobs passed in [push CI](https://github.com/abanerjee23/UnLoop/actions/runs/37628510417) and [PR CI](https://github.com/abanerjee23/UnLoop/actions/runs/37628516842). |

## Checks run

| Command/check | Result |
|---|---|
| `uv run --frozen ruff check backend scripts` | Pass |
| `TEST_DATABASE_URL=… REQUIRE_POSTGRES_TESTS=true uv run pytest -q` | **69 passed**, including real PostgreSQL and actual API-process restart; no skips |
| `uv run --frozen python -m unloop.fixture_check` | **24 labelled cases**, 12/12 split, zero model runs |
| `uv run --frozen python -m unloop.worker --check` | Pass; still explicitly no queue |
| `npm run build --prefix frontend` | TypeScript/Vite pass, 35 modules |
| `TEST_DATABASE_URL=… npm test --prefix frontend` | **7 passed**: two retained preview checks plus five real workspace checks |
| Real HTTP health/readiness/create/reopen | Pass in API smoke/process/browser tests |
| `docker compose config --quiet` | Pass; local database only |
| `alembic upgrade head` / repeat / metadata check | Pass on PostgreSQL 17 |
| Source preservation | Build plan, A1 schema/checker/fixtures/archive unchanged against baseline |

Local runtime: Python 3.12.12, Node 25.9.0, npm 11.12.1, uv 0.11.7, PostgreSQL 17 in a disposable local Docker container bound to `127.0.0.1:15432`. Hosted CI used Node 22 and independent PostgreSQL services; backend and browser jobs passed for `8484701`. Tests use isolated random schemas, not application rows. API/browser processes are stopped after checks. One dependency deprecation warning from Starlette's HTTPX test compatibility is non-failing; it is not an application failure or quality metric.

Fresh screenshots are generated and ignored at `artifacts/local/phase1a-desktop.png` and `phase1a-mobile.png`; they were visually inspected for readable controls, layout and overflow. They are local evidence, not deployed assets. Test durations are not product latency or savings metrics. No model/provider experiment ran; model tokens/cost are not measured or inferred.

## Decisions and limits

- Deterministic header intake avoids adding model access/cost before the ownership foundation. Common explicit English/ISO date patterns work; other formats require review/correction. No unrestricted natural-language understanding is claimed.
- Session TTL defaults to 28,800 seconds, configurable 60–86,400; no sliding extension. Expiry denies access but does not automatically delete retained rows. New sessions cannot recover earlier rows. Wider deletion/retention/backup policy remains future work before real-data intake.
- Secure cookies default on; explicit insecure HTTP development is allowed only for localhost origins. Exact origin and CSRF protections are tested. No Supabase Auth or production multi-user/organization security claim.
- Seeded employee grade C, predefined display identities. Persona toggle deliberately lets the same demo owner use both views; server checks apply to the current persona and every object.
- Proposal HMAC-SHA256 signing uses a separate private per-session secret stored in PostgreSQL; the visible CSRF token cannot sign proposals. Original chat descriptions/proposals are not persisted as reports; corrected confirmed headers are.
- Only draft report status/version 1 exists. No fake submissions, approval amounts, upload controls, Gmail connections or worker outputs are added. Future schema changes belong to later migrations.
- Provider-specific Supabase sign-off is outstanding. Baseline and feature branch are published with a draft PR and passing CI for the Linux import fix. Codex Cloud connector/environment setup remains pending; no Cloud review result is claimed.

## Remaining sign-off

Configure a non-production Supabase PostgreSQL connection securely, apply the migration, run the API and confirm/list/reload/restart a report with the same live session, then repeat owner/manager access checks. Record the actual target/run evidence without credentials or raw report text. Baseline and feature branch were published on user authorization; [draft PR #1](https://github.com/abanerjee23/UnLoop/pull/1) and its CI are available. Complete the separate Cloud environment setup and run the requested review. Do not start 1B or 1C as part of resolving this report.
