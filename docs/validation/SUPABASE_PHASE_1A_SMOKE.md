# Opt-in live Supabase Phase 1A smoke

Prepared 7 October 2026 (Europe/London) for project `lchwjzunjqtakjdnzrze` and draft [PR #1](https://github.com/abanerjee23/UnLoop/pull/1). **Live Supabase remains UNVERIFIED.** This is a concrete check prepared for private secret setup and review, not a provider success claim.

Cloud cannot directly reach the public PostgreSQL target through its supported network policy. This preparation does not extract/transfer the personal Cloud vault value, change network policy, or introduce a VPN, relay or infrastructure. No live connection/schema/data operation was attempted.

## Private setup after reviewing this check

In the **abanerjee23/UnLoop** repository (not Un-Loop):

1. Open [Settings → Secrets and variables → Actions → Secrets](https://github.com/abanerjee23/UnLoop/settings/secrets/actions). Add a **repository secret** named `SUPABASE_SMOKE_DATABASE_URL`, privately supplying the intended project's PostgreSQL connection URI. Do not paste it into chat, a commit, issue, command line or workflow file; this task does not retrieve it from Cloud.
2. Prefer Supabase's **Session pooler** connection on explicit port **5432**, database `postgres`, username `postgres.lchwjzunjqtakjdnzrze`. GitHub-hosted runners commonly need this IPv4-capable route; the direct hostname `db.lchwjzunjqtakjdnzrze.supabase.co` with username `postgres` is also accepted but reachability is not assumed. Port 6543 transaction pooling is deliberately rejected. Use a properly URL-encoded password and include `?sslmode=require` (or `verify-ca`/`verify-full` if runner certificate trust is configured). Only `sslmode` query parameters are accepted; host/service/options overrides are rejected. Use a controlled non-production project/login with permission to create/drop an isolated schema and run these migrations.
3. Open [Actions → Variables](https://github.com/abanerjee23/UnLoop/settings/variables/actions). After review, add the **repository variable** `RUN_SUPABASE_SMOKE` with value exactly `true`. This variable is not a secret. Leave it absent/false until ready.
4. Request a harmless normal commit/push on existing `codex/phase-1a` after setup. The existing registered `Checks` workflow runs on that push. No workflow dispatch on an unmerged new workflow, default-main change, merge, worktree or deployment is needed. Do not rely on rerunning an earlier skipped job to pick up changed opt-in settings.

The `supabase-smoke` job runs only for repository `abanerjee23/UnLoop`, event `push`, ref `refs/heads/codex/phase-1a`, opt-in `true`, and successful ordinary backend/frontend jobs. Otherwise GitHub displays the live job as **skipped**; that is not provider evidence. The secret is provided only to the live script step, not checkout/setup, ordinary CI, pull-request/fork events or browser tests. Remove/set the variable false after the gate if recurring branch-push execution is no longer desired. No automatic merge follows success.

## Execution and assertions

Live job command: `uv run --frozen python -m scripts.supabase_smoke`.

The script requires the exact project via the direct hostname or recognized Supabase pooler hostname plus project-specific username, port 5432, database postgres, password and TLS-required mode. Missing/invalid setup fails before connecting. It rejects libpq query overrides of host/user/service/search_path. `pg_stat_ssl` must report TLS active on the actual admin and isolated test connection. `sslmode=require` proves encryption, not certificate identity verification; use a configured verify mode when that separate property is needed.

`scripts/postgres_test_support.py` creates a fresh random `unloop_test_<32 hex>` schema. The scoped URL selects only that schema (no public fallback) with SQL/lock timeouts. Before Alembic runs, `current_schema()` must match the generated name and live TLS must be active. A session pooler that rejects/ignores startup options fails safely; compatibility is not presumed. Schema creation/cleanup uses explicitly quoted generated identifiers. No public-schema migration or existing report query is authorized by this check.

Assertions use only synthetic report text:

- Migration reaches `0002_phase1a_hardening` and real FastAPI HTTP readiness agrees.
- Server and stored employee grade are C; attempted client grade assignment is rejected.
- Proposal and rejected implicit confirmation create zero report rows.
- Explicit confirmation succeeds; list and re-fetch match the saved header.
- First Uvicorn subprocess exits; a second process reuses the same session cookie and returns the identical report/list.
- Session B has an empty list and cannot read session A's report (404).
- Persisted manager persona has an empty list, cannot read drafts, propose or confirm a report (403).

The helper attempts to drop only the schema created by this invocation on success and ordinary assertion/migration failures. Both API processes stop before cleanup. Success is emitted only after cleanup succeeds. A runner hard kill or database outage can prevent cleanup; no script can guarantee remote cleanup in those conditions, and such a run must not be counted as passing. It never attempts broad cleanup of other test schemas or public data.

Connections time out in five seconds; SQL/locks in ten/five seconds; HTTP requests in ten seconds; API readiness in twenty seconds; process shutdown in five seconds before kill. The Linux CLI has a 180-second deadline and the GitHub job a five-minute limit. Parent library logging is suppressed during the CLI run, child stdout/stderr are discarded, access logs are disabled and only the scoped DB URL plus minimal runtime settings reach the child. No connection URL, exception string/traceback, environment dump, cookie, CSRF token, synthetic report body or raw SQL is printed. Failure output contains fixed stage/error codes; transport/storage failures deliberately omit their underlying exception details.

A passing live result identifies `mode: live_supabase`, the expected project, `tls: true`, migration revision, completed HTTP/restart/ownership/grade checks and successful schema cleanup. Inspect the actual run/commit and record its URL before closing the provider gate. A local pass, skipped job, secret presence or workflow file alone never closes it.

## Fresh local evidence

The clearly separate command `uv run --frozen python -m scripts.supabase_smoke --local-test` reads only `TEST_DATABASE_URL`. It requires localhost and disposable database name `unloop_smoke_test`, and is forbidden when `CI` or `GITHUB_ACTIONS` is set. The live job never passes this flag or reads `TEST_DATABASE_URL` as a fallback.

Using restored native PostgreSQL 17.11 on localhost in this Cloud task, the standalone local command passed and reported `mode: local_test_not_provider_evidence`, `tls: false`, revision 0002 and successful cleanup. Actual PostgreSQL/HTTP regressions include the complete smoke/restart, injected assertion failure cleanup and refusal of an unencrypted connection before creating a schema. An ignored-search_path simulation uses real PostgreSQL connections and verifies migrations do not run and only the new schema is removed. Target/sanitization tests are guard tests, not provider connectivity evidence.

Frozen sync, Ruff, full backend suite (**113 passed, zero skips**; one existing dependency deprecation warning), 24-case fixture integrity (12/12 split, zero model runs), worker check, npm ci/build and all Chromium tests (**7 passed, zero skips**, five real API/PostgreSQL workspace flows) passed. The original 88 backend tests remain included. Native runtime and pinned Chromium are as recorded in the Phase 1A Cloud hardening evidence. The disposable local database is removed after validation.
