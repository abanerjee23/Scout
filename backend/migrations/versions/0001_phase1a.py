"""Demo sessions, seeded profiles and confirmed drafts only."""

import sqlalchemy as sa
from alembic import op

revision = "0001_phase1a"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_sessions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("proposal_secret", sa.String(64), nullable=False),
        sa.Column("active_persona", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("active_persona IN ('employee', 'manager')", name="session_persona"),
        sa.CheckConstraint("expires_at > created_at", name="session_expiry"),
    )
    op.create_index("ix_demo_sessions_expires_at", "demo_sessions", ["expires_at"])
    op.create_table(
        "demo_profiles",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("demo_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("persona", sa.String(16), nullable=False),
        sa.Column("display_name", sa.String(80), nullable=False),
        sa.Column("grade", sa.String(1), nullable=True),
        sa.UniqueConstraint("session_id", "persona", name="profile_owner_persona"),
        sa.UniqueConstraint("session_id", "id", name="profile_owner_id"),
        sa.CheckConstraint(
            "(persona = 'employee' AND grade = 'C') OR (persona = 'manager' AND grade IS NULL)",
            name="profile_seeded_grade",
        ),
    )
    op.create_table(
        "reports",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "session_id",
            sa.Uuid(),
            sa.ForeignKey("demo_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("employee_profile_id", sa.Uuid(), nullable=False),
        sa.Column("confirmation_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("business_purpose", sa.String(500), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "employee_profile_id"],
            ["demo_profiles.session_id", "demo_profiles.id"],
            name="report_employee_owner",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("session_id", "confirmation_id", name="report_confirmation_once"),
        sa.CheckConstraint("end_date >= start_date", name="report_date_order"),
        sa.CheckConstraint("char_length(btrim(name)) BETWEEN 3 AND 120", name="report_name_length"),
        sa.CheckConstraint(
            "char_length(btrim(business_purpose)) BETWEEN 5 AND 500", name="report_purpose_length"
        ),
        sa.CheckConstraint("status = 'draft' AND version = 1", name="report_phase1a_state"),
    )
    op.create_index("ix_reports_session_id", "reports", ["session_id"])


def downgrade():
    op.drop_table("reports")
    op.drop_table("demo_profiles")
    op.drop_table("demo_sessions")
