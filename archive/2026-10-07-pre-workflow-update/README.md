# Unloop

AI-assisted expense preparation, policy guidance and line-specific clarification.

**Phase 0 scaffold.** The React preview displays synthetic expected outcomes. Flask exposes a health endpoint. There is no sign-in, receipt upload, database persistence, live extraction, FX lookup or approval yet. Disabled controls make those boundaries explicit.

## Run locally

Requirements: Node 22.12+ (Node 22 LTS used by CI), uv and Python 3.12. uv can install the pinned Python version. Commands below run from the repository root unless shown otherwise.

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

Open http://127.0.0.1:5173. Vite proxies `/api` to Flask on port 5001. Both servers bind to localhost. These are development servers, not production deployment commands. Stop each with Ctrl+C.

No credentials are needed for this preview. Future service variables are listed in [.env.example](.env.example); do not commit real secrets. The scaffold does not automatically load an .env file.

## Validate

```sh
uv run ruff check backend scripts
uv run pytest -q
uv run python -m unloop.fixture_check
uv run python -m unloop.worker --check
npm run build --prefix frontend
cd frontend
npx playwright install chromium
npm test
```

Browser tests check expected-amount presentation, scenario selection, evidence visibility, API failure copy and mobile overflow. They stub the health response; separately check the real endpoint with `curl http://127.0.0.1:5001/api/health`.

The fixture command checks 24 source/label scenarios (12 development, 12 held-out). Passing it proves fixture integrity and expected-value reconciliation, **not model quality**. No model has run. See [fixture guidance](fixtures/meals/README.md) before using the held-out set.

Render synthetic development receipt images from their transcripts:

```sh
uv run python scripts/render_receipts.py
```

Outputs go to ignored `artifacts/local/receipts`. These initial images are uniform bootstrap material; real image diversity and actual blur/multi-page cases must be added before vision-quality claims.

## Code map

- `backend/unloop/__init__.py`: Flask application factory and health route.
- `backend/unloop/contracts.py`: strict A1 Meal output schema and evidence/revision gates. Air/GT enum values are retained but processing is unsupported in this first slice.
- `backend/unloop/fixture_check.py`: offline fixture validator. Its cap arithmetic is a label-consistency check, not the production policy service.
- `backend/unloop/worker.py`: checkable worker entry point; the PostgreSQL queue arrives in Phase 1.
- `frontend/src/`: React receipt/claim preview. Static illustrations are not model output or editable financial records.
- `fixtures/meals/`: synthetic source transcripts and separate expected labels.
- `backend/tests/`, `frontend/tests/`: contract/API and browser checks.
- `.github/workflows/checks.yml`: checks ready for a future GitHub remote; no remote or hosted CI run exists yet.

SQLAlchemy/Alembic, the PostgreSQL adapter and the Agents SDK will be added with their actual integrations. No unused integration is installed solely to appear complete.

## Phase 0 choices and remaining setup

- Candidate upload limits: 10 MiB per document, 10 pages; PDF/JPEG/PNG. The API has a request-size ceiling but no upload route yet. File signatures/page enforcement belong to Phase 1 and must be verified against examples.
- A1 schema uses decimal strings, evidence references and explicit missing/ambiguous states. A valid reference proves location, not that the fact was read correctly. Currency membership, human-field locks and full document-role gates remain Phase 2 work.
- Financial examples use exact pennies. No unapproved rounding convention or policy effective date is embedded in the implementation.
- Visual direction: white evidence surface `#ffffff`, pale blue workspace `#f3f6f8`, slate text `#173244`, teal claim value `#17675f`, amber pending feedback `#80500a`. System Avenir/Segoe UI keeps the preview independent of remote font downloads. Left-aligned expense facts sit beside the source receipt; the receipt/claim comparison is the main emphasis. Browser checks cover a narrow viewport and keyboard focus is visible.

Run `uv run python -m unloop.doctor` for a secret-safe environment-presence check. Configuration presence is not authenticated access.

| Service | Needed for | Current verification |
|---|---|---|
| Supabase Auth/PostgreSQL | Phase 1 | No project connection or credentials configured by this scaffold |
| OpenAI | Phase 2 | Exact available Luna API model and account access not verified |
| Galileo | Phase 2 | Project and ingestion access not verified |
| Frankfurter/ECB and Open Exchange Rates | Phase 2 | No live rate calls or fallback authentication verified |
| Railway | Deployment | No services provisioned |

Configure external accounts through their secure setup flows; don't paste credentials into chat. Phase 0 completion does not depend on those services.

## Product and implementation records

[Build plan](BUILD_PLAN.md) · [Iteration log](PRODUCT_ITERATION_LOG.md) · [Vision](Unloop_Vision.md) · [Architecture](Architecture.md) · [Policy](Synthetic_T&E_Policy.md) · [Receipt agent contract](Receipt_Extraction_Agent.md)

Scaffold references checked during implementation: [Flask application factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/), [Flask testing](https://flask.palletsprojects.com/en/stable/testing/) and [Vite setup](https://vite.dev/guide/).
