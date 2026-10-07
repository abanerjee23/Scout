"""Only Phase 1A entities: isolated sessions, seeded personas and confirmed reports."""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
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
