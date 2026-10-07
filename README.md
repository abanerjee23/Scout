# Unloop

AI-assisted expense preparation, in-context policy guidance and line-specific review.

Full-version repository: [abanerjee23/UnLoop](https://github.com/abanerjee23/UnLoop). Delivery follows [build → test → commit → push → check CI → repeat](docs/product/DELIVERY_WORKFLOW.md), shipping small working increments within each phase. The separate hackathon repository is abanerjee23/Un-Loop.

**Current implementation: Phase 0 scaffold.** React displays synthetic expected Meal outcomes and Flask exposes a health endpoint. This repository does not yet implement the persona toggle, chat report creation, receipt upload, Gmail intake, persistence, live extraction, FX or manager approval. Disabled controls make the synthetic preview boundary explicit.

**Current design:** Employee/Manager toggle without app login; Astra proposes a confirmed report header without manager details; optional Gmail and chat/workspace JPEG/PNG/PDF uploads; chat clarifications automatically open the relevant expense; employee explicitly submits; manager approves all or eligible selected lines; both personas receive in-app inbox events. Learning from corrections is excluded. Railway hosts the web service and worker.

## Documentation

Only these four documentation files remain at the repository root:

| Document | Purpose |
|---|---|
| [Unloop_Vision.md](Unloop_Vision.md) | Product scope, user journey and agreed decisions |
| [Architecture.md](Architecture.md) | Component authority, session/data boundaries and integrations |
| [BUILD_PLAN.md](BUILD_PLAN.md) | Phased delivery, acceptance gates and implementation status |
| [README.md](README.md) | Repository navigation, current capabilities and run instructions |

Supporting documents are grouped in [docs](docs/README.md):

- [Agent contract](docs/agents/Receipt_Extraction_Agent.md)
- [Synthetic policy](docs/policy/Synthetic_T&E_Policy.md)
- [Gmail integration design](docs/integrations/GMAIL.md)
- [Product iteration log](docs/product/PRODUCT_ITERATION_LOG.md) and [delivery workflow](docs/product/DELIVERY_WORKFLOW.md)
- [Phase 0 validation](docs/validation/ITER-001_VALIDATION.md) and [documentation update validation](docs/validation/DOCS_UPDATE_VALIDATION.md)

Previous versions and outdated architecture diagrams are preserved in [archive](archive/README.md). Historical snapshots are not current requirements. The hackathon plan in the separate UnLoop folder is reference-only and was not modified. Active code, dependency/configuration files and local development assets stay in their existing folders; this organization does not restructure the application.

## Run the current scaffold

Requirements: Node 22.12+ and Python 3.12 with uv. Commands run from the repository root unless noted.

```sh
uv sync --frozen
npm ci --prefix frontend
```

Terminal 1:

```sh
uv run flask --app unloop run --host 127.0.0.1 --port 5001
```

Terminal 2:

```sh
npm run dev --prefix frontend
```

Open http://127.0.0.1:5173. Vite proxies `/api` to Flask on port 5001. Both development servers bind to localhost; these are not production deployment commands. No credentials are needed for the synthetic preview. Keep real values in ignored environment files/server configuration, never in docs or chat. The scaffold does not automatically load an `.env` file.

## Scaffold checks

```sh
uv run ruff check backend scripts
uv run pytest -q
uv run python -m unloop.fixture_check
uv run python -m unloop.worker --check
npm run build --prefix frontend
```

Browser checks:

```sh
cd frontend
npx playwright install chromium
npm test
```

Browser tests cover static expected-value presentation, scenario selection, evidence visibility, API failure copy and mobile overflow. They stub health responses; separately check the real Flask endpoint with `curl http://127.0.0.1:5001/api/health`. Tests do not prove a live receipt-processing flow.

The fixture checker validates 24 scenarios, twelve development/twelve held-out. It proves fixture integrity, not model accuracy. [Fixture guidance](fixtures/meals/README.md) describes dataset separation and gaps. Render development receipt images with:

```sh
uv run python scripts/render_receipts.py
```

Generated images/screenshots remain in ignored `artifacts/local/`. Uniform bootstrap images are insufficient to claim robustness to actual photos/PDFs. Candidate upload bounds are 10 MiB/file, ten pages and ten files/batch; enforcement is future Phase 1 work. The current request-size ceiling alone is not proof of validated upload handling.

## Code map

| Folder | Current purpose |
|---|---|
| `frontend/` | React synthetic receipt/claim preview and browser checks |
| `backend/unloop/` | Flask health route, A1 Meal output schema, fixture validator and checkable worker stub |
| `backend/tests/` | Contract, fixture and health-route tests |
| `backend/migrations/` | Phase 1 migration guidance; no initialized database yet |
| `fixtures/meals/` | Separate development/held-out transcripts and labels |
| `scripts/` | Receipt fixture renderer |
| `.github/workflows/` | Scaffold CI configuration; no hosted CI execution claimed |
| `artifacts/local/` | Ignored generated development evidence |
| `docs/` | Active supporting contracts, integration guidance and evidence |
| `archive/` | Frozen superseded docs/diagrams, with checksums |

SQLAlchemy/Alembic, the PostgreSQL adapter and Agents SDK are added when their actual integration is built. A valid evidence location in the current schema does not prove a model read it correctly; locked-human-field, currency membership and complete document-role gates still need implementation.

## Service setup and honest status

| Service | Current evidence | Next proof |
|---|---|---|
| Supabase PostgreSQL | Selected for storage; no connection demonstrated in this repository | Migrations, persistence and cross-session access tests in Phase 1 |
| Google/Gmail | User-confirmed existing GCP setup for aban.hackathon@gmail.com; configured reference implementation in separate hackathon app | Python callback/token lifecycle and real attachment bytes; then Railway callback/scan |
| OpenAI | Selected runtime; no model run in this scaffold | Pin actual API model identifier and run/evaluate A1 in Phase 2 |
| Galileo | Existing project-specific diagnostic/eval choice | Trace integration, minimization and failure handling from first live AI run |
| Historical FX | Frankfurter/ECB plus Open Exchange Rates fallback selected | Real primary/fallback adapters and exact-date behaviour in Phase 2 |
| Railway | Selected host; separate hackathon deployment does not validate this app | Hosted web/worker journey and OAuth callback |

The `.env.example` and `doctor` script are historical scaffold setup aids, not a complete revised configuration contract. They still contain Supabase Auth-related variables from the earlier design; those do not require restoring employee/manager login. Running `uv run python -m unloop.doctor` reports inherited variable presence only and attempts no connections. Update configuration adapters/templates with actual Phase 1 implementation rather than claiming they are already wired.

The [Gmail design](docs/integrations/GMAIL.md) specifies future server-only OAuth client, callback and token-key configuration, scan permissions and production ownership gates. Never copy secrets into this repository. Exact callbacks must match the Python/Railway deployment; the hackathon callback is not assumed compatible.

## Next action

Begin revised Phase 1: isolated demo sessions, top persona toggle, confirmed chat-created reports and durable shared evidence intake. [Build plan](BUILD_PLAN.md) records phase gates. [ITER-002](docs/product/PRODUCT_ITERATION_LOG.md#iter-002--workflow-reconciliation-and-document-organization) records the 7 October docs reconciliation; no app implementation or live integrations are completed by that cycle.
