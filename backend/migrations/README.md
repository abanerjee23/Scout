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
