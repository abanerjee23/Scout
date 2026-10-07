"""Session-owned reports, retained evidence and leased validation jobs."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
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
        CheckConstraint("source IN ('chat', 'workspace')", name="evidence_source"),
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
