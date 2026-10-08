# Opt-in live Supabase Phase 1A smoke

Current status, 8 October: PR #1 and PR #2 are merged. Phase 1A and the subsequent [Phase 1B live provider gate](PHASE_1B_VALIDATION.md) passed at their recorded commits; the opt-in job remains disabled after success. The workflow still limits live smoke to `codex/phase-1b`; it is not a current app-schema, Railway or Gmail proof. The Phase 1A instructions/results below are dated evidence.

## Verified live provider evidence — 7 October 2026

**VERIFIED** at exact commit `8a88ac5eb3c1c41954f7a93654576df18a163e05` on `codex/phase-1a`: [hosted push run 37652912234](https://github.com/abanerjee23/UnLoop/actions/runs/37652912234), [live job 112901079685](https://github.com/abanerjee23/UnLoop/actions/runs/37652912234/job/112901079685). At `2026-10-07T16:34:43.9015201Z` (17:34 Europe/London), the job emitted:

```json
{"status":"passed","mode":"live_supabase","project":"lchwjzunjqtakjdnzrze","tls":true,"migration":"0002_phase1a_hardening","http_restart_ownership_grade":true,"schema_cleanup":true}
```

Hosted backend **152 passed, zero skips** and Chromium **7 passed, zero skips**; Ruff, build, fixture integrity and worker checks passed. This proves synthetic isolated-schema persistence over client TLS, migration, explicit confirmation, list/re-fetch, process restart, ownership/persona/fixed-grade boundaries and cleanup against the live provider. It does not prove a deployed UI, production operation or public-schema migrations. Astra header intake remains deterministic; no live model was called. Phase 1B/1C are not implemented.

After success the owner set `RUN_SUPABASE_SMOKE=false`; the repository secret remains private. Subsequent documentation pushes intentionally skip the live job while ordinary CI runs. Earlier failures and local-only results below are historical evidence, not outstanding provider blockers. Deployment and its production configuration remain separate work; PR #1 stays draft and unmerged.

Cloud did not retrieve/transfer the provider credential or connect directly; the live job used the privately saved GitHub secret. Global Cloud network restrictions remain unchanged.

## Private setup reference (completed; opt-in now disabled)

In the **abanerjee23/UnLoop** repository (not Un-Loop):

1. Open [Settings → Secrets and variables → Actions → Secrets](https://github.com/abanerjee23/UnLoop/settings/secrets/actions). Add a **repository secret** named `SUPABASE_SMOKE_DATABASE_URL`, privately supplying the intended project's PostgreSQL connection URI. Do not paste it into chat, a commit, issue, command line or workflow file; this task does not retrieve it from Cloud.
2. Prefer Supabase's **Session pooler** connection on explicit port **5432**, database `postgres`, username `postgres.lchwjzunjqtakjdnzrze`. GitHub-hosted runners commonly need this IPv4-capable route; the direct hostname `db.lchwjzunjqtakjdnzrze.supabase.co` with username `postgres` is also accepted but reachability is not assumed. Port 6543 transaction pooling is deliberately rejected. Use a properly URL-encoded password. The script adds `sslmode=require` internally when omitted; an explicit `verify-ca`/`verify-full` is preserved if runner certificate trust is configured. Explicit insecure modes and duplicate TLS parameters are rejected. Only `sslmode` query parameters are accepted; host/service/options overrides are rejected. Use a controlled non-production project/login with permission to create/drop an isolated schema and run these migrations.
3. Open [Actions → Variables](https://github.com/abanerjee23/UnLoop/settings/variables/actions). After review, add the **repository variable** `RUN_SUPABASE_SMOKE` with value exactly `true`. This variable is not a secret. Leave it absent/false until ready.
4. Request a harmless normal commit/push on existing `codex/phase-1a` after setup. The existing registered `Checks` workflow runs on that push. No workflow dispatch on an unmerged new workflow, default-main change, merge, worktree or deployment is needed. Do not rely on rerunning an earlier skipped job to pick up changed opt-in settings.

The `supabase-smoke` job runs only for repository `abanerjee23/UnLoop`, event `push`, ref `refs/heads/codex/phase-1a`, opt-in `true`, and successful ordinary backend/frontend jobs. Otherwise GitHub displays the live job as **skipped**; that is not provider evidence. The secret is provided only to the live script step, not checkout/setup, ordinary CI, pull-request/fork events or browser tests. Remove/set the variable false after the gate if recurring branch-push execution is no longer desired. No automatic merge follows success.

## Execution and assertions

Live job command: `uv run --frozen python -m scripts.supabase_smoke`.

The script requires the exact project via the direct hostname or recognized Supabase pooler hostname plus project-specific username, port 5432, database postgres, password and TLS-required mode. An omitted TLS mode is normalized internally to `require` without printing the URL. The live URL also internally forces `gssencmode=disable`, so GSS encryption cannot substitute for SSL. Other missing/invalid setup fails before connecting. It rejects libpq query overrides of host/user/service/search_path. `connection.connection.driver_connection.pgconn.ssl_in_use` must report negotiated client TLS on both admin and isolated psycopg connections. This verifies the client-to-pooler hop; PostgreSQL `pg_stat_ssl` may describe the separate pooler-to-database hop. Missing, false, unknown or unreadable driver TLS state fails closed with fixed diagnostic codes. `sslmode=require` proves encryption, not certificate identity verification; use a configured verify mode when that separate property is needed.

`scripts/postgres_test_support.py` creates a fresh random `unloop_test_<32 hex>` schema. Startup options are not used. A SQLAlchemy connect hook explicitly selects only that schema with parameterized `set_config`, sets SQL/lock timeouts, verifies `current_schema()`, and commits the session state on every new DBAPI connection. The helper and both API processes use the same strictly validated `UNLOOP_TEST_SCHEMA` (only `unloop_test_<32 hex>`); it is internal process configuration, never an HTTP input. Before Alembic runs, `current_schema()` must match the generated name and live TLS must be active. Failed selection blocks migrations/application queries without a public fallback. Schema creation/cleanup uses explicitly quoted generated identifiers. No public-schema migration or existing report query is authorized by this check.

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

## Historical preparation and local evidence

The clearly separate command `uv run --frozen python -m scripts.supabase_smoke --local-test` reads only `TEST_DATABASE_URL`. It requires localhost and disposable database name `unloop_smoke_test`, and is forbidden when `CI` or `GITHUB_ACTIONS` is set. The live job never passes this flag or reads `TEST_DATABASE_URL` as a fallback.

Using restored native PostgreSQL 17.11 on localhost in this Cloud task, the standalone local command passed and reported `mode: local_test_not_provider_evidence`, `tls: false`, revision 0002 and successful cleanup. Actual PostgreSQL/HTTP regressions include the complete smoke/restart, injected assertion failure cleanup and refusal of an unencrypted connection before creating a schema. An ignored-search_path simulation uses real PostgreSQL connections and verifies migrations do not run and only the new schema is removed. Target/sanitization tests are guard tests, not provider connectivity evidence.

Frozen sync, Ruff, full backend suite (**113 passed, zero skips**; one existing dependency deprecation warning), 24-case fixture integrity (12/12 split, zero model runs), worker check, npm ci/build and all Chromium tests (**7 passed, zero skips**, five real API/PostgreSQL workspace flows) passed. The original 88 backend tests remain included. Native runtime and pinned Chromium are as recorded in the Phase 1A Cloud hardening evidence. The disposable local database is removed after validation.

TLS normalization follow-up: an omitted TLS query is now strengthened internally to `sslmode=require`; no secret re-entry is needed. Targeted smoke guards passed **30 tests** and the full backend passed **118 tests, zero skips**, under CI environment flags with required disposable native PostgreSQL. Explicit insecure/duplicate modes remain rejected and live negotiated client TLS checks remain mandatory. This local result does not establish live Supabase success.

Safe diagnostics follow-up: failures now identify a fixed stage (admin/scoped connection, TLS, schema creation/search_path, migration, HTTP start/flow/restart or cleanup) and allowlisted code such as `auth_failed`, `connection_timeout`, `network_unreachable`, `unsupported_startup_parameter` or `permission_denied`. Driver SQLSTATE/message inspection is internal only; no raw exception, SQL, URL or credential is emitted. After a direct-target transport failure only, a credential-free DNS subprocess bounded to three seconds may identify `ipv6_only_direct_target`; this is a diagnostic, not an automatic hostname/login rewrite. **52 targeted smoke/diagnostic tests passed, zero skips**, including real local smoke/cleanup and credential-bearing exception guards; Ruff passed. At that point live provider success was pending; the verified run above closes that gate.

Client TLS follow-up: verified installed psycopg 3.3.6 binary exposes `pgconn.ssl_in_use`; no FFI is used. Admin/scoped checks now prove the negotiated client hop instead of querying upstream `pg_stat_ssl`, and the live URL forces GSS encryption off. **59 targeted tests passed, zero skips**, Ruff passed, and the real disposable native PostgreSQL HTTP/restart smoke passed with cleanup. The non-TLS native server refused libpq `sslmode=require` with `gssencmode=disable`. Provider success was pending at this historical point; see the verified run above.

Session-pooler selection follow-up: **89 targeted smoke/diagnostic/intake tests passed, zero skips**, and Ruff passed. Real native PostgreSQL verified operation without startup options, committed session selection on reuse and engine reconnect, two-process HTTP restart persistence, missing-schema refusal and cleanup when schema selection is bypassed. Provider success was pending at this historical point; see the verified run above.

Shared-caller follow-up: hosted run 37652435672 found unscoped recreated app engines after startup options were removed (**42 failed / 110 passed**); its live job correctly skipped. All isolated fixture, hardening app, process-restart and real browser-server consumers now derive the verified schema from their isolated engine and explicitly pass it to each app/process. Full local CI-flagged backend: **152 passed, zero skips**, with `REQUIRE_POSTGRES_TESTS=true`. All Chromium browser tests: **7 passed, zero skips**, including real API/PostgreSQL flows. Frozen sync, Ruff, fixture integrity (24 cases; zero model runs), worker check, npm ci/build passed. That gate subsequently passed in the verified run above.
