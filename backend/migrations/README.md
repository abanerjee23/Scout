# PostgreSQL migrations

Phase 1A uses SQLAlchemy and Alembic. The API is FastAPI/Python, per the user's explicit backend choice. `0001_phase1a` creates only `demo_sessions`, `demo_profiles` and `reports`. Profiles are seeded transactionally when a session is created. No Supabase Auth, evidence, jobs, Gmail, expense or approval tables are included.

Run from the repository root with a securely configured non-production PostgreSQL connection:

```sh
uv run --env-file .env alembic upgrade head
uv run --env-file .env alembic current
uv run --env-file .env alembic check
```

The app does not apply migrations/create tables on startup. Back up any retained data before schema changes; `downgrade base` deletes all Phase 1A data and is for disposable test databases only. Do not run it against retained application data. The test runner creates its own random schema, executes the real migration, validates metadata alignment and drops only that schema after tests.

Cookie bearers are random and hashed in storage; sessions expire at a fixed absolute time. Employee/manager profiles belong to that same owner. Grade C is fixed by server seeding and a database check. Reports use an owner-constrained profile foreign key, explicit date/length checks and a unique owner/confirmation pair. Read/write ownership/persona/CSRF rules are enforced by the API; database credentials remain server-only.

Expiry blocks access and clears the cookie. Expired rows are retained in this demo; no automatic data-deletion/backup-restore feature is claimed. Establish the broader retention policy before real-data/Gmail intake. A manually deleted session cascades to its profiles/reports. No endpoint exposes that deletion in 1A.

SQLite cannot substitute for PostgreSQL test evidence. Local PostgreSQL checks do not prove Supabase connectivity; record the separate live Supabase smoke before declaring that gate complete.

`0002_phase1a_hardening` tightens employee grade to non-null C and adds an employee-persona foreign key independently of the existing report owner constraint. This was the Phase 1A readiness revision; current readiness requires the latest 0003 revision. Upgrade backfills previously allowed null employee grades to C and same-owner manager report references to the existing seeded employee. If that employee is missing, upgrade fails transactionally without inventing an identity or deleting a report; explicitly repair the affected demo owner before retrying. Downgrade removes the added schema constraints/column but retains repaired values. PostgreSQL regressions cover fresh upgrade, populated `0001` upgrade, downgrade/re-upgrade, metadata alignment and atomic failure.


`0003_phase1b_evidence` adds only documents, separate original bytes, report/source provenance links and revision-bound validation jobs, plus the report owner/id key needed by composite ownership foreign keys. Existing Phase 1A rows are preserved; no backfill is required. Fresh and 0002 upgrades, downgrade/re-upgrade and Alembic metadata checks pass. Downgrading to 0002 deliberately deletes all Phase 1B evidence/jobs but retains sessions/profiles/reports; use only with a backup or disposable test state. Queue results use leases/tokens/revisions, not exactly-once execution. No Gmail, expense, submission or approval tables are created here.

`0004_phase1c_gmail` adds encrypted session-owned connections and scans; `0005_phase2_meals` adds receipt suggestions, calculations, locked revisions and budget reservations; `0006_phase3_categories` adds paused travel states; `0007_phase4_policy` adds versioned questions/chunks without enabling an extension; `0008_phase5_review` adds explicit submitted line snapshots, persona inbox events, questions, immutable releases/Meal slots and processing-ready records. Current readiness requires 0008. Submitted and approved payloads are protected by database triggers, in addition to API revision/role gates. A downgrade of 0008 refuses to run after any submission exists. Preserve review history and verified backups; do not downgrade a populated approval database. Session deletion would be rejected by immutable-history triggers once submissions exist; no automatic deletion/retention workflow is implemented.
