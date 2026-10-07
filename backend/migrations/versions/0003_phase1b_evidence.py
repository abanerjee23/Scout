"""Phase 1B evidence and leased validation jobs"""

import sqlalchemy as sa
from alembic import op

revision = "0003_phase1b_evidence"
down_revision = "0002_phase1a_hardening"
branch_labels = None
depends_on = None


def upgrade():
    # All new evidence is phase-scoped; no future submission/approval entities.
    op.create_unique_constraint("report_owner_id", "reports", ["session_id", "id"])
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'application/pdf')", name="document_mime"
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'processing', 'validated', 'failed')", name="document_state"
        ),
        sa.CheckConstraint(
            "byte_size BETWEEN 1 AND 10485760 AND page_count BETWEEN 1 AND 10",
            name="document_limits",
        ),
        sa.CheckConstraint("revision > 0", name="document_revision"),
        sa.ForeignKeyConstraint(["session_id"], ["demo_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "id", name="document_owner_id"),
        sa.UniqueConstraint("session_id", "sha256", name="document_owner_hash"),
    )
    op.create_table(
        "document_bytes",
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("document_id"),
    )
    op.create_table(
        "evidence_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(state = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="job_lease_state",
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'processing', 'validated', 'failed')", name="job_state"
        ),
        sa.CheckConstraint("attempts BETWEEN 0 AND 3 AND revision > 0", name="job_bounds"),
        sa.ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="job_document_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "revision", name="job_document_revision_once"),
    )
    op.create_table(
        "evidence_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("filename", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("source IN ('chat', 'workspace')", name="evidence_source"),
        sa.ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="evidence_document_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "report_id"],
            ["reports.session_id", "reports.id"],
            name="evidence_report_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "report_id", "document_id", "source", name="evidence_report_source_once"
        ),
    )


def downgrade():
    # Downgrade intentionally removes only Phase 1B evidence/jobs.
    op.drop_table("evidence_links")
    op.drop_table("evidence_jobs")
    op.drop_table("document_bytes")
    op.drop_table("documents")
    op.drop_constraint("report_owner_id", "reports", type_="unique")
