"""Session-owned reports, retained evidence and leased validation jobs."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class DemoSession(Base):
    __tablename__ = "demo_sessions"
    __table_args__ = (
        CheckConstraint("active_persona IN ('employee', 'manager')", name="session_persona"),
        CheckConstraint("expires_at > created_at", name="session_expiry"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    proposal_secret: Mapped[str] = mapped_column(String(64))
    active_persona: Mapped[str] = mapped_column(String(16), default="employee")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class DemoProfile(Base):
    __tablename__ = "demo_profiles"
    __table_args__ = (
        UniqueConstraint("session_id", "persona", name="profile_owner_persona"),
        UniqueConstraint("session_id", "id", name="profile_owner_id"),
        UniqueConstraint("id", "persona", name="profile_id_persona"),
        CheckConstraint(
            "(persona = 'employee' AND grade IS NOT NULL AND grade = 'C') "
            "OR (persona = 'manager' AND grade IS NULL)",
            name="profile_seeded_grade",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"))
    persona: Mapped[str] = mapped_column(String(16))
    display_name: Mapped[str] = mapped_column(String(80))
    grade: Mapped[str | None] = mapped_column(String(1))


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "employee_profile_id"],
            ["demo_profiles.session_id", "demo_profiles.id"],
            name="report_employee_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["employee_profile_id", "employee_persona"],
            ["demo_profiles.id", "demo_profiles.persona"],
            name="report_employee_persona",
            ondelete="CASCADE",
        ),
        CheckConstraint("employee_persona = 'employee'", name="report_employee_only"),
        UniqueConstraint("session_id", "confirmation_id", name="report_confirmation_once"),
        UniqueConstraint("session_id", "id", name="report_owner_id"),
        CheckConstraint("end_date >= start_date", name="report_date_order"),
        CheckConstraint("char_length(btrim(name)) BETWEEN 3 AND 120", name="report_name_length"),
        CheckConstraint(
            "char_length(btrim(business_purpose)) BETWEEN 5 AND 500", name="report_purpose_length"
        ),
        CheckConstraint("status = 'draft' AND version = 1", name="report_phase1a_state"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_sessions.id", ondelete="CASCADE"), index=True
    )
    employee_profile_id: Mapped[UUID]
    employee_persona: Mapped[str] = mapped_column(String(16), server_default="employee")
    confirmation_id: Mapped[UUID]
    name: Mapped[str] = mapped_column(String(120))
    start_date: Mapped[date]
    end_date: Mapped[date]
    business_purpose: Mapped[str] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(16), default="draft")
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        UniqueConstraint("session_id", "sha256", name="document_owner_hash"),
        UniqueConstraint("session_id", "id", name="document_owner_id"),
        CheckConstraint(
            "mime_type IN ('image/jpeg', 'image/png', 'application/pdf')", name="document_mime"
        ),
        CheckConstraint(
            "byte_size BETWEEN 1 AND 10485760 AND page_count BETWEEN 1 AND 10",
            name="document_limits",
        ),
        CheckConstraint(
            "state IN ('queued', 'processing', 'validated', 'failed')", name="document_state"
        ),
        CheckConstraint("revision > 0", name="document_revision"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"))
    sha256: Mapped[str] = mapped_column(String(64))
    mime_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int]
    page_count: Mapped[int]
    filename: Mapped[str] = mapped_column(String(120))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    revision: Mapped[int] = mapped_column(default=1)
    failure_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentBytes(Base):
    __tablename__ = "document_bytes"
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    content: Mapped[bytes] = mapped_column(LargeBinary)


class EvidenceLink(Base):
    __tablename__ = "evidence_links"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "report_id"],
            ["reports.session_id", "reports.id"],
            name="evidence_report_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="evidence_document_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("report_id", "document_id", "source", name="evidence_report_source_once"),
        CheckConstraint("source IN ('chat', 'workspace', 'gmail')", name="evidence_source"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID]
    report_id: Mapped[UUID]
    document_id: Mapped[UUID]
    source: Mapped[str] = mapped_column(String(16))
    filename: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceJob(Base):
    __tablename__ = "evidence_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="job_document_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("document_id", "revision", name="job_document_revision_once"),
        CheckConstraint(
            "state IN ('queued', 'processing', 'validated', 'failed')", name="job_state"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3 AND revision > 0", name="job_bounds"),
        CheckConstraint(
            "(state = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="job_lease_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID]
    document_id: Mapped[UUID]
    revision: Mapped[int]
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GmailConnection(Base):
    __tablename__ = "gmail_connections"
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("demo_sessions.id", ondelete="CASCADE"), primary_key=True
    )
    version: Mapped[UUID] = mapped_column(default=uuid4)
    credential_revision: Mapped[int] = mapped_column(default=1)
    mailbox: Mapped[str | None] = mapped_column(String(100))
    encrypted_tokens: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(32), default="disconnected")
    __table_args__ = (
        CheckConstraint("credential_revision > 0", name="gmail_credential_revision"),
        CheckConstraint(
            "status IN ('connected', 'disconnected', 'reconnect_required')",
            name="gmail_connection_status",
        ),
        CheckConstraint(
            "(status = 'connected' AND encrypted_tokens IS NOT NULL "
            "AND key_version IS NOT NULL AND mailbox = 'aban.hackathon@gmail.com') "
            "OR (status != 'connected' AND encrypted_tokens IS NULL AND key_version IS NULL)",
            name="gmail_token_state",
        ),
    )


class GmailOAuthState(Base):
    __tablename__ = "gmail_oauth_states"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("demo_sessions.id", ondelete="CASCADE"))
    connection_version: Mapped[UUID]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used: Mapped[bool] = mapped_column(default=False)


class GmailScan(Base):
    __tablename__ = "gmail_scans"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "report_id"],
            ["reports.session_id", "reports.id"],
            name="gmail_scan_report_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("session_id", "id", name="gmail_scan_owner_id"),
        CheckConstraint(
            "state IN ('queued', 'processing', 'complete', 'partial', 'failed', 'cancelled')",
            name="gmail_scan_state",
        ),
        CheckConstraint(
            "attempts BETWEEN 0 AND 3 AND cursor BETWEEN 0 AND 15 "
            "AND imported BETWEEN 0 AND 10 AND byte_count BETWEEN 0 AND 41943040",
            name="gmail_scan_bounds",
        ),
        CheckConstraint(
            "(state = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="gmail_scan_lease",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID]
    report_id: Mapped[UUID]
    report_fingerprint: Mapped[str] = mapped_column(String(64))
    connection_version: Mapped[UUID]
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    message_ids: Mapped[list | None] = mapped_column(JSON)
    cursor: Mapped[int] = mapped_column(default=0)
    imported: Mapped[int] = mapped_column(default=0)
    skipped: Mapped[int] = mapped_column(default=0)
    byte_count: Mapped[int] = mapped_column(default=0)
    truncated: Mapped[bool] = mapped_column(default=False)
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class GmailImport(Base):
    __tablename__ = "gmail_imports"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "scan_id"],
            ["gmail_scans.session_id", "gmail_scans.id"],
            name="gmail_import_scan_owner",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            name="gmail_import_document_owner",
            ondelete="CASCADE",
        ),
        UniqueConstraint("scan_id", "message_id", "attachment_id", name="gmail_import_once"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID]
    scan_id: Mapped[UUID]
    document_id: Mapped[UUID]
    mailbox: Mapped[str] = mapped_column(String(100))
    message_id: Mapped[str] = mapped_column(String(200))
    attachment_id: Mapped[str] = mapped_column(String(512))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sha256: Mapped[str] = mapped_column(String(64))
    review_required: Mapped[bool] = mapped_column(default=True)


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "report_id"],
            ["reports.session_id", "reports.id"],
            ondelete="CASCADE",
            name="expense_report_owner",
        ),
        ForeignKeyConstraint(
            ["session_id", "document_id"],
            ["documents.session_id", "documents.id"],
            ondelete="CASCADE",
            name="expense_document_owner",
        ),
        UniqueConstraint("session_id", "document_id", name="expense_receipt_once"),
        UniqueConstraint("session_id", "id", name="expense_owner_id"),
        CheckConstraint("version > 0", name="expense_version"),
        CheckConstraint(
            "state IN ('queued','processing','needs_information','review','failed','unsupported',"
            "'unreadable','policy_inactive','conversion_pending','excluded','conflict','noncompliant','profile_incomplete')",
            name="expense_state",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID]
    report_id: Mapped[UUID]
    document_id: Mapped[UUID]
    version: Mapped[int] = mapped_column(default=1)
    revision_id: Mapped[UUID] = mapped_column(default=uuid4)
    state: Mapped[str] = mapped_column(String(32), default="queued")
    facts: Mapped[dict] = mapped_column(JSON, default=dict)
    locks: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[dict] = mapped_column(JSON, default=dict)
    confirmed: Mapped[bool] = mapped_column(default=False)
    issues: Mapped[list] = mapped_column(JSON, default=list)
    calculation: Mapped[dict | None] = mapped_column(JSON)
    failure_code: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExpenseRevision(Base):
    __tablename__ = "expense_revisions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "expense_id"],
            ["expenses.session_id", "expenses.id"],
            ondelete="CASCADE",
            name="revision_expense_owner",
        ),
        UniqueConstraint("expense_id", "version", name="expense_revision_once"),
        UniqueConstraint("expense_id", "id", name="revision_expense_id"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID]
    expense_id: Mapped[UUID]
    version: Mapped[int]
    snapshot: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExpenseJob(Base):
    __tablename__ = "expense_jobs"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "expense_id"],
            ["expenses.session_id", "expenses.id"],
            ondelete="CASCADE",
            name="job_expense_owner",
        ),
        UniqueConstraint("expense_id", "revision_id", "kind", name="expense_job_once"),
        UniqueConstraint("id", "revision_id", name="job_revision_id"),
        ForeignKeyConstraint(
            ["expense_id", "revision_id"],
            ["expense_revisions.expense_id", "expense_revisions.id"],
            ondelete="CASCADE",
            name="job_expense_revision",
        ),
        CheckConstraint("kind IN ('extract','calculate')", name="expense_job_kind"),
        CheckConstraint(
            "state IN ('queued','processing','complete','failed')", name="expense_job_state"
        ),
        CheckConstraint("attempts BETWEEN 0 AND 3", name="expense_job_attempts"),
        CheckConstraint(
            "(state = 'processing' AND lease_token IS NOT NULL AND lease_until IS NOT NULL) "
            "OR (state != 'processing' AND lease_token IS NULL AND lease_until IS NULL)",
            name="expense_job_lease",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    session_id: Mapped[UUID]
    expense_id: Mapped[UUID]
    revision_id: Mapped[UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(16))
    state: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None]
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failure_code: Mapped[str | None] = mapped_column(String(40))
    reserved_usd: Mapped[str | None] = mapped_column(String(40))
    call_count: Mapped[int] = mapped_column(default=0)


class ExtractionSuggestion(Base):
    __tablename__ = "extraction_suggestions"
    __table_args__ = (
        UniqueConstraint("job_id", name="suggestion_job_once"),
        ForeignKeyConstraint(
            ["job_id", "revision_id"],
            ["expense_jobs.id", "expense_jobs.revision_id"],
            ondelete="CASCADE",
            name="suggestion_job_revision",
        ),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("expense_jobs.id", ondelete="CASCADE"))
    revision_id: Mapped[UUID] = mapped_column()
    output: Mapped[dict] = mapped_column(JSON)
    diagnostics: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ModelBudget(Base):
    __tablename__ = "model_budgets"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    calls: Mapped[int] = mapped_column(default=0)
    reserved_usd: Mapped[str] = mapped_column(String(40), default="0")


class FxObservation(Base):
    __tablename__ = "fx_observations"
    __table_args__ = (
        UniqueConstraint("currency", "rate_date", "provider", name="fx_observation_once"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    currency: Mapped[str] = mapped_column(String(3))
    rate_date: Mapped[date]
    provider: Mapped[str] = mapped_column(String(32))
    rate: Mapped[str] = mapped_column(String(60))
    source: Mapped[str] = mapped_column(String(200))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class MealPolicyVersion(Base):
    __tablename__ = "meal_policy_versions"
    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    effective_date: Mapped[date]
    rounding: Mapped[str] = mapped_column(String(40))
    facts: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ExpenseCalculation(Base):
    """Append-only numeric result tied to its exact fact revision."""

    __tablename__ = "expense_calculations"
    __table_args__ = (UniqueConstraint("revision_id", name="calculation_revision_once"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    revision_id: Mapped[UUID] = mapped_column(
        ForeignKey("expense_revisions.id", ondelete="CASCADE")
    )
    result: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
