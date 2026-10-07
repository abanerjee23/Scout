# Migrations

Phase 1 will initialize Alembic against Supabase PostgreSQL. The current demo uses
server-owned sessions and predefined employee/manager personas, without Supabase
employee/manager login. Tables and ownership rules follow the
[architecture](../../Architecture.md) and [build plan](../../BUILD_PLAN.md).

No migration or database connection runs in Phase 0. Do not substitute SQLite
and describe it as proof of Supabase persistence, session isolation or Gmail
integration. Only explicit submitted snapshots become visible in manager mode.
