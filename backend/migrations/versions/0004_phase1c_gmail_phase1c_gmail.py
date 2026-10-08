"""phase1c_gmail"""

import sqlalchemy as sa
from alembic import op

revision = "0004_phase1c_gmail"
down_revision = "0003_phase1b_evidence"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("evidence_source", "evidence_links", type_="check")
    op.create_check_constraint(
        "evidence_source", "evidence_links", "source IN ('chat', 'workspace', 'gmail')"
    )

    op.create_table(
        "gmail_connections",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Uuid(), nullable=False),
        sa.Column("credential_revision", sa.Integer(), nullable=False),
        sa.Column("mailbox", sa.String(length=100), nullable=True),
        sa.Column("encrypted_tokens", sa.LargeBinary(), nullable=True),
        sa.Column("key_version", sa.String(length=32), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.CheckConstraint(
            "(status = 'connected' AND encrypted_tokens IS NOT NULL "
            "AND key_version IS NOT NULL AND mailbox = 'aban.hackathon@gmail.com') "
            "OR (status != 'connected' AND encrypted_tokens IS NULL AND key_version IS NULL)",
            name="gmail_token_state",
        ),
        sa.CheckConstraint(
            "status IN ('connected', 'disconnected', 'reconnect_required')",
            name="gmail_connection_status",
        ),
        sa.CheckConstraint("credential_revision > 0", name="gmail_credential_revision"),
        sa.ForeignKeyConstraint(["session_id"], ["demo_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_table(
        "gmail_oauth_states",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("connection_version", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["demo_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_table(
        "gmail_scans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("report_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("connection_version", sa.Uuid(), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("message_ids", sa.JSON(), nullable=True),
        sa.Column("cursor", sa.Integer(), nullable=False),
        sa.Column("imported", sa.Integer(), nullable=False),
        sa.Column("skipped", sa.Integer(), nullable=False),
        sa.Column("byte_count", sa.Integer(), nullable=False),
        sa.Column("truncated", sa.Boolean(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", sa.Uuid(), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=32), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(state = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="gmail_scan_lease",
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'processing', 'complete', 'partial', 'failed', 'cancelled')",
            name="gmail_scan_state",
        ),
        sa.CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND cursor BETWEEN 0 AND 15 "
            "AND imported BETWEEN 0 AND 10 AND byte_count BETWEEN 0 AND 41943040",
            name="gmail_scan_bounds",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "report_id"],
            ["reports.session_id", "reports.id"],
            name="gmail_scan_report_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "id", name="gmail_scan_owner_id"),
    )
    op.create_table(
        "gmail_imports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("scan_id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("mailbox", sa.String(length=100), nullable=False),
        sa.Column("message_id", sa.String(length=200), nullable=False),
        sa.Column("attachment_id", sa.String(length=512), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("review_required", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="gmail_import_document_owner",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["session_id", "scan_id"],
            ["gmail_scans.session_id", "gmail_scans.id"],
            name="gmail_import_scan_owner",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("scan_id", "message_id", "attachment_id", name="gmail_import_once"),
    )


def downgrade():
    # Retain original bytes; remove Gmail-only provenance/link references on downgrade.
    op.execute("DELETE FROM evidence_links WHERE source = 'gmail'")
    op.drop_constraint("evidence_source", "evidence_links", type_="check")
    op.create_check_constraint(
        "evidence_source", "evidence_links", "source IN ('chat', 'workspace')"
    )

    op.drop_table("gmail_imports")
    op.drop_table("gmail_scans")
    op.drop_table("gmail_oauth_states")
    op.drop_table("gmail_connections")
