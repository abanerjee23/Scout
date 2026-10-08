"""phase2_meal_workflow"""

import sqlalchemy as sa
from alembic import op

revision = "0005_phase2_meals"
down_revision = "0004_phase1c_gmail"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fx_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("rate_date", sa.Date(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("rate", sa.String(length=60), nullable=False),
        sa.Column("source", sa.String(length=200), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("currency", "rate_date", "provider", name="fx_observation_once"),
    )
    op.create_table(
        "meal_policy_versions",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("effective_date", sa.Date(), nullable=False),
        sa.Column("rounding", sa.String(length=40), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "model_budgets",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("calls", sa.Integer(), nullable=False),
        sa.Column("reserved_usd", sa.String(length=40), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_table(
        "expenses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.Column("locks", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("confirmed", sa.Boolean(), nullable=False),
        sa.Column("issues", sa.JSON(), nullable=False),
        sa.Column("calculation", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(length=40), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('queued','processing','needs_information','review','failed','unsupported',"
            "'unreadable','policy_inactive','conversion_pending','excluded','conflict')",
            name="expense_state",
        ),
        sa.CheckConstraint("version > 0", name="expense_version"),
        sa.ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="expense_document_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "report_id"],
            ["reports.session_id", "reports.id"],
            name="expense_report_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "document_id", name="expense_receipt_once"),
        sa.UniqueConstraint("session_id", "id", name="expense_owner_id"),
    )
    op.create_table(
        "expense_revisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "expense_id"],
            ["expenses.session_id", "expenses.id"],
            name="revision_expense_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("expense_id", "version", name="expense_revision_once"),
    )
    op.create_table(
        "expense_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("expense_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=40), nullable=True),
        sa.Column("reserved_usd", sa.String(length=40), nullable=True),
        sa.Column("call_count", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "(state = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="expense_job_lease",
        ),
        sa.CheckConstraint("kind IN ('extract','calculate')", name="expense_job_kind"),
        sa.CheckConstraint(
            "state IN ('queued','processing','complete','failed')", name="expense_job_state"
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3", name="expense_job_attempts"),
        sa.ForeignKeyConstraint(
            ["session_id", "expense_id"],
            ["expenses.session_id", "expenses.id"],
            name="job_expense_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("expense_id", "revision_id", "kind", name="expense_job_once"),
    )
    op.create_table(
        "extraction_suggestions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("output", sa.JSON(), nullable=False),
        sa.Column("diagnostics", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["expense_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", name="suggestion_job_once"),
    )
    op.create_table(
        "expense_calculations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("revision_id", sa.Uuid(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["expense_revisions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", name="calculation_revision_once"),
    )
    op.create_unique_constraint("revision_expense_id", "expense_revisions", ["expense_id", "id"])
    op.create_unique_constraint("job_revision_id", "expense_jobs", ["id", "revision_id"])
    op.create_foreign_key(
        "job_expense_revision",
        "expense_jobs",
        "expense_revisions",
        ["expense_id", "revision_id"],
        ["expense_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "suggestion_job_revision",
        "extraction_suggestions",
        "expense_jobs",
        ["job_id", "revision_id"],
        ["id", "revision_id"],
        ondelete="CASCADE",
    )
    op.execute(
        "CREATE FUNCTION reject_meal_policy_mutation() RETURNS trigger LANGUAGE plpgsql AS $$ "
        "BEGIN RAISE EXCEPTION 'Meal policy versions are immutable'; END $$"
    )
    op.execute(
        "CREATE TRIGGER immutable_meal_policy BEFORE UPDATE OR DELETE ON meal_policy_versions "
        "FOR EACH ROW EXECUTE FUNCTION reject_meal_policy_mutation()"
    )


def downgrade():
    op.drop_table("expense_calculations")
    op.drop_table("extraction_suggestions")
    op.drop_table("expense_jobs")
    op.drop_table("expense_revisions")
    op.drop_table("expenses")
    op.drop_table("model_budgets")
    op.drop_table("meal_policy_versions")
    op.execute("DROP FUNCTION reject_meal_policy_mutation()")
    op.drop_table("fx_observations")
