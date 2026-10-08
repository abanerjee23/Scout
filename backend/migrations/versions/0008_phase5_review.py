"""Explicit submission, review, immutable release snapshots and processing-ready records."""

import sqlalchemy as sa
from alembic import op

revision = "0008_phase5_review"
down_revision = "0007_phase4_policy"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("report_phase1a_state", "reports", type_="check")
    op.alter_column("reports", "status", type_=sa.String(24), existing_type=sa.String(16))
    op.create_check_constraint(
        "report_workflow_state",
        "reports",
        "status IN ('draft','submitted','partially_approved','approved') AND version > 0",
    )
    op.drop_constraint("expense_state", "expenses", type_="check")
    op.create_check_constraint(
        "expense_state",
        "expenses",
        "state IN "
        "('queued','processing','needs_information','review','failed','unsupported','unreadable','policy_inactive','conversion_pending','excluded','conflict','noncompliant','profile_incomplete','approved')",
    )
    op.execute("""
CREATE TABLE submissions (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        report_id UUID NOT NULL,
        request_id UUID NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        version INTEGER NOT NULL,
        header JSON NOT NULL,
        total_gbp VARCHAR(40) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT submission_report_owner FOREIGN KEY(session_id, report_id) REFERENCES
        reports (session_id, id) ON DELETE CASCADE,
        CONSTRAINT submission_report_version UNIQUE (report_id, version),
        CONSTRAINT submission_request_once UNIQUE (session_id, request_id),
        CONSTRAINT submission_owner_id UNIQUE (session_id, id)
)
""")
    op.execute("""
CREATE TABLE submitted_lines (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        submission_id UUID NOT NULL,
        expense_id UUID NOT NULL,
        revision_id UUID NOT NULL,
        snapshot JSON NOT NULL,
        state VARCHAR(16) NOT NULL,
        version INTEGER NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT submitted_line_owner FOREIGN KEY(session_id, submission_id) REFERENCES
        submissions (session_id, id) ON DELETE CASCADE,
        CONSTRAINT submitted_expense_owner FOREIGN KEY(session_id, expense_id) REFERENCES
        expenses (session_id, id) ON DELETE CASCADE,
        CONSTRAINT submitted_expense_revision FOREIGN KEY(expense_id, revision_id) REFERENCES
        expense_revisions (expense_id, id) ON DELETE CASCADE,
        CONSTRAINT submitted_expense_once UNIQUE (submission_id, expense_id),
        CONSTRAINT submitted_line_owner_id UNIQUE (session_id, id),
        CONSTRAINT submitted_line_state CHECK (state IN
        ('pending','held','returned','approved','superseded')),
        CONSTRAINT submitted_line_version CHECK (version > 0)
)
""")
    op.execute("""
CREATE TABLE approval_releases (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        report_id UUID NOT NULL,
        request_id UUID NOT NULL,
        request_hash VARCHAR(64) NOT NULL,
        version INTEGER NOT NULL,
        snapshot JSON NOT NULL,
        total_gbp VARCHAR(40) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT release_report_owner FOREIGN KEY(session_id, report_id) REFERENCES reports
        (session_id, id) ON DELETE CASCADE,
        CONSTRAINT release_request_once UNIQUE (session_id, request_id),
        CONSTRAINT release_report_version UNIQUE (report_id, version),
        CONSTRAINT release_owner_id UNIQUE (session_id, id)
)
""")
    op.execute("""
CREATE TABLE approved_lines (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        release_id UUID NOT NULL,
        expense_id UUID NOT NULL,
        revision_id UUID NOT NULL,
        snapshot JSON NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT approved_release_owner FOREIGN KEY(session_id, release_id) REFERENCES
        approval_releases (session_id, id) ON DELETE CASCADE,
        CONSTRAINT approved_expense_owner FOREIGN KEY(session_id, expense_id) REFERENCES
        expenses (session_id, id) ON DELETE CASCADE,
        CONSTRAINT approved_expense_revision FOREIGN KEY(expense_id, revision_id) REFERENCES
        expense_revisions (expense_id, id) ON DELETE CASCADE,
        CONSTRAINT expense_approved_once UNIQUE (expense_id)
)
""")
    op.execute("""
CREATE TABLE approved_meal_slots (
        session_id UUID NOT NULL,
        receipt_date DATE NOT NULL,
        meal_type VARCHAR(16) NOT NULL,
        expense_id UUID NOT NULL,
        PRIMARY KEY (session_id, receipt_date, meal_type),
        CONSTRAINT approved_meal_expense_owner FOREIGN KEY(session_id, expense_id) REFERENCES
        expenses (session_id, id) ON DELETE CASCADE,
        CONSTRAINT approved_meal_type CHECK (meal_type IN ('breakfast','lunch','dinner')),
        FOREIGN KEY(session_id) REFERENCES demo_sessions (id) ON DELETE CASCADE,
        UNIQUE (expense_id),
        FOREIGN KEY(expense_id) REFERENCES expenses (id) ON DELETE CASCADE
)
""")
    op.execute("""
CREATE TABLE processing_ready (
        release_id UUID NOT NULL,
        state VARCHAR(16) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (release_id),
        CONSTRAINT processing_not_payment CHECK (state = 'ready'),
        FOREIGN KEY(release_id) REFERENCES approval_releases (id) ON DELETE CASCADE
)
""")
    op.execute("""
CREATE TABLE review_questions (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        line_id UUID NOT NULL,
        request_id UUID NOT NULL,
        question VARCHAR(1000) NOT NULL,
        response VARCHAR(1500),
        version INTEGER NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT review_question_owner FOREIGN KEY(session_id, line_id) REFERENCES
        submitted_lines (session_id, id) ON DELETE CASCADE,
        CONSTRAINT review_question_request_once UNIQUE (session_id, request_id)
)
""")
    op.execute("""
CREATE TABLE inbox_events (
        id UUID NOT NULL,
        session_id UUID NOT NULL,
        report_id UUID NOT NULL,
        persona VARCHAR(16) NOT NULL,
        event_key VARCHAR(100) NOT NULL,
        payload JSON NOT NULL,
        read BOOLEAN NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        CONSTRAINT inbox_report_owner FOREIGN KEY(session_id, report_id) REFERENCES reports
        (session_id, id) ON DELETE CASCADE,
        CONSTRAINT inbox_event_once UNIQUE (session_id, persona, event_key),
        CONSTRAINT inbox_persona CHECK (persona IN ('employee','manager'))
)
""")
    op.execute("""
CREATE FUNCTION reject_release_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Submitted and approved snapshots are immutable'; END $$
""")
    for table in [
        "submissions",
        "approval_releases",
        "approved_lines",
        "approved_meal_slots",
        "processing_ready",
    ]:
        op.execute(
            f"CREATE TRIGGER immutable_snapshot BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION reject_release_mutation()"
        )
    op.execute("""
CREATE FUNCTION protect_submitted_snapshot() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Submitted snapshots are immutable'; END IF;
  IF NEW.snapshot::jsonb IS DISTINCT FROM OLD.snapshot::jsonb OR NEW.id != OLD.id
    OR NEW.session_id != OLD.session_id OR NEW.submission_id != OLD.submission_id
    OR NEW.expense_id != OLD.expense_id OR NEW.revision_id != OLD.revision_id
    OR OLD.state = 'approved'
  THEN RAISE EXCEPTION 'Submitted payload and approved state are immutable'; END IF;
  RETURN NEW;
END $$
""")
    op.execute(
        "CREATE TRIGGER protect_payload BEFORE UPDATE OR DELETE ON "
        "submitted_lines FOR EACH ROW EXECUTE FUNCTION "
        "protect_submitted_snapshot()"
    )


def downgrade():
    if op.get_bind().scalar(sa.text("SELECT EXISTS (SELECT 1 FROM submissions)")):
        raise RuntimeError("Cannot downgrade after submission: preserve immutable review history")
    op.drop_table("inbox_events")
    op.drop_table("review_questions")
    op.drop_table("processing_ready")
    op.drop_table("approved_meal_slots")
    op.drop_table("approved_lines")
    op.drop_table("approval_releases")
    op.drop_table("submitted_lines")
    op.drop_table("submissions")
    op.execute("DROP FUNCTION protect_submitted_snapshot()")
    op.execute("DROP FUNCTION reject_release_mutation()")
    op.execute("UPDATE reports SET status = 'draft', version = 1")
    op.drop_constraint("report_workflow_state", "reports", type_="check")
    op.alter_column("reports", "status", type_=sa.String(16), existing_type=sa.String(24))
    op.create_check_constraint(
        "report_phase1a_state", "reports", "status = 'draft' AND version = 1"
    )
    op.execute("UPDATE expenses SET state = 'review' WHERE state = 'approved'")
    op.drop_constraint("expense_state", "expenses", type_="check")
    op.create_check_constraint(
        "expense_state",
        "expenses",
        "state IN "
        "('queued','processing','needs_information','review','failed','unsupported','unreadable','policy_inactive','conversion_pending','excluded','conflict','noncompliant','profile_incomplete')",
    )
