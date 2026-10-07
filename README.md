# Unloop

Expense report preparation with an Employee/Manager demo workspace.

**Current implementation: Phase 1A on FastAPI/Python.** An employee can describe a report to Astra, review/correct its name, explicit dates and business purpose, confirm it, and reopen the saved report. PostgreSQL owns sessions, profiles and reports. Manager mode cannot inspect employee drafts. This is a persona demonstration, not production multi-user authentication.

Astra report intake is **deterministic**, with no model/API call: it recognizes supported explicit date formats and asks for review when fields are missing or ambiguous. Confirmation and database writes belong to application code. No manager details are requested.

**Not implemented:** uploads, Gmail, extraction, policy assessment, FX, submission, approval, Teams, RAG, durable worker processing or Railway deployment. The separately labelled synthetic Meal preview remains at `/?preview=1`; its values are expected outcomes, not extracted/saved expenses.

Local PostgreSQL integration and real API/browser checks pass. **Supabase connectivity and hosted CI are separate, unverified gates** until configured/executed; this does not claim full Phase 1 completion. See [Phase 1A validation](docs/validation/PHASE_1A_VALIDATION.md).

Full-version repository: [abanerjee23/UnLoop](https://github.com/abanerjee23/UnLoop). The separate hackathon repository `abanerjee23/Un-Loop` is outside this work.

## Run the workspace

Requirements: Python 3.12/uv, Node 22.12+ and PostgreSQL. Docker Compose is a local database option; no worktree is required. From the repository root:

```sh
uv sync --frozen
npm ci --prefix frontend
docker compose up -d --wait
cp .env.example .env
```

For the local Compose database, set these server-only values in the ignored `.env`:

```dotenv
DATABASE_URL=postgresql://unloop:unloop_local_dev@127.0.0.1:15432/unloop
TEST_DATABASE_URL=postgresql://unloop:unloop_local_dev@127.0.0.1:15432/unloop
APP_ORIGIN=http://127.0.0.1:5173
SESSION_COOKIE_SECURE=false
SESSION_TTL_SECONDS=28800
```

These are public local-development credentials for a database bound to localhost. For a non-production Supabase database, configure its actual PostgreSQL connection/TLS options securely instead. Do not paste real service credentials into docs/chat or put them in frontend variables. No Supabase Auth keys, model keys or Gmail credentials are needed for 1A.

Apply migrations explicitly before starting the API:

```sh
uv run --env-file .env alembic upgrade head
uv run --env-file .env uvicorn unloop:create_app --factory --host 127.0.0.1 --port 5001
```

In another terminal:

```sh
npm run dev --prefix frontend
```

Open [the workspace](http://127.0.0.1:5173). Vite proxies `/api` to FastAPI on port 5001. Use the exact `APP_ORIGIN`; a different hostname such as `localhost` versus `127.0.0.1` is a different origin. The app does not silently load `.env`; the `uv --env-file` commands do.

Try: “Prepare my London expense report for 1–4 October 2026 for a client workshop.” Review/correct the proposed header, then choose **Confirm and create report**. Reload or use Your reports to reopen it. Switch to Manager: drafts disappear and direct draft API reads are blocked. Switch back to Employee to reopen them.

The default session lasts eight hours from creation, without sliding renewal. Its opaque bearer is in a host-only httpOnly SameSite=Lax cookie; only its SHA256 hash is stored. Secure cookies are the default. `SESSION_COOKIE_SECURE=false` is permitted only for explicit HTTP localhost development. Mutations require the exact allowed Origin, JSON and a session-bound CSRF header; bootstrap requires Origin/JSON before any cookie exists. Unknown/expired sessions are rejected and their cookies cleared. Starting a new session does not recover expired-session reports. Fixed demo grade C is server-seeded and not editable.

`GET /api/health` is liveness only. `GET /api/readiness` checks migrated PostgreSQL; unavailable storage gives recoverable 503 copy. The API never creates tables automatically. `docker compose stop` retains local DB data; do not remove its volume unless you intentionally want to discard local demo data.

## Deterministic intake boundary

Supported date input: `2026-10-01 to 2026-10-04`, `1–4 October 2026`, `30 September 2026 to 4 October 2026`, and a single explicit date for a one-day report. English month names are supported. Relative dates, ambiguous numeric dates, missing years and partly specified ranges are not guessed; fill the review fields instead. Years must be 2000–2100; end must not precede start. Report names are 3–120 characters, purpose 5–500, with whitespace trimmed and control characters rejected.

A proposal makes no report write. A signed session-bound proposal expires after 20 minutes. Explicit confirmation revalidates all header fields and creates a draft. Repeating the same confirmation returns the same report; changing an already confirmed proposal gives 409. Owner-row locking and a database uniqueness constraint protect concurrent confirmation. Session/identity/grade/manager fields supplied by a client are rejected.

## Validate

```sh
uv run --env-file .env ruff check backend scripts
uv run --env-file .env pytest -q
uv run python -m unloop.fixture_check
uv run python -m unloop.worker --check
npm run build --prefix frontend
cd frontend
npx playwright install chromium
cd ..
uv run --env-file .env -- npm test --prefix frontend
```

`TEST_DATABASE_URL` must reference a dedicated test/development PostgreSQL database. Tests create/drop uniquely named schemas and apply actual Alembic migrations; they never truncate application tables in the public schema. The backend tests cover cookie/expiry, CSRF, ownership, grade/persona spoofing, validation, concurrent confirmation and restart. Browser workspace tests start a real API with a separate disposable schema and do not intercept report/session responses. Ports 5001 and 5173 must be free during browser tests.

Without `TEST_DATABASE_URL`, integration/browser workspace tests explicitly skip; that is not a passing 1A persistence gate. CI supplies PostgreSQL 17 and fails if required DB configuration is absent. The two retained preview tests stub health only. Screenshots/build output stay ignored. The worker remains a check-only scaffold; no queue was implemented.

The fixture checker validates 24 labelled Meals (12 development / 12 held-out), **not model quality**. The A1 v0.1 schema and fixtures remain unchanged. Do not feed held-out expected labels into UI/model input. [Fixture guidance](fixtures/meals/README.md) records diversity and integration gaps.

## Code and documentation map

| Path | Purpose |
|---|---|
| `backend/unloop/api.py` | Authorized sessions/personas/proposals/confirmed reports/readiness |
| `backend/unloop/database.py`, `models.py` | PostgreSQL configuration and Phase 1A-only entities |
| `backend/unloop/intake.py` | Pydantic inputs and bounded deterministic parsing |
| `backend/migrations/` | Alembic initial migration; [migration instructions](backend/migrations/README.md) |
| `frontend/src/components/` | Astra intake, report list and saved workspace |
| `frontend/src/SyntheticPreview.tsx` | Retained Phase 0 preview, separate from saved data |
| `backend/tests/`, `frontend/tests/` | Deterministic, PostgreSQL, process-restart and browser checks |
| `scripts/browser_test_server.py` | Real API/disposable DB for browser tests |
| `.github/workflows/checks.yml` | Backend and browser CI with independent PostgreSQL services |

Sources of truth: [vision](Unloop_Vision.md), [architecture](Architecture.md), [build plan](BUILD_PLAN.md), [A1 contract](docs/agents/Receipt_Extraction_Agent.md), [policy](docs/policy/Synthetic_T&E_Policy.md), [Gmail design](docs/integrations/GMAIL.md). The user-requested FastAPI replacement is recorded in architecture/iteration evidence; the build plan is preserved unchanged.

[Historical audit](docs/product/CURRENT_STATE_AND_EXECUTION_PLAN.md), [iteration log](docs/product/PRODUCT_ITERATION_LOG.md), [delivery workflow](docs/product/DELIVERY_WORKFLOW.md), [supporting docs](docs/README.md), [archive](archive/README.md).

## Next gate

Verify the same migration/session/confirmed-report/reopen journey on securely configured non-production Supabase PostgreSQL, and publish/check the feature branch CI when Git delivery is authorized. Phase 1B is the next implementation increment after 1A gates are satisfied; it has not been started here.
