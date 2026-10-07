"""Enforce fixed employee grade and employee-only report profile references."""

import sqlalchemy as sa
from alembic import op

revision = "0002_phase1a_hardening"
down_revision = "0001_phase1a"
branch_labels = None
depends_on = None


def upgrade():
    # Repair only the previously allowed NULL grade using the fixed demo seed.
    op.execute("UPDATE demo_profiles SET grade = 'C' WHERE persona = 'employee' AND grade IS NULL")
    # Preserve report identity and owner; replace any same-owner manager reference
    # with that owner's seeded employee. Missing employee profiles fail the new FK.
    op.execute("""
        UPDATE reports AS r SET employee_profile_id = e.id
        FROM demo_profiles AS p, demo_profiles AS e
        WHERE r.employee_profile_id = p.id AND p.persona = 'manager'
          AND e.session_id = r.session_id AND e.persona = 'employee'
    """)
    op.drop_constraint("profile_seeded_grade", "demo_profiles", type_="check")
    op.create_check_constraint(
        "profile_seeded_grade",
        "demo_profiles",
        "(persona = 'employee' AND grade IS NOT NULL AND grade = 'C') "
        "OR (persona = 'manager' AND grade IS NULL)",
    )
    op.create_unique_constraint("profile_id_persona", "demo_profiles", ["id", "persona"])
    op.add_column(
        "reports",
        sa.Column("employee_persona", sa.String(16), nullable=False, server_default="employee"),
    )
    op.create_check_constraint("report_employee_only", "reports", "employee_persona = 'employee'")
    op.create_foreign_key(
        "report_employee_persona",
        "reports",
        "demo_profiles",
        ["employee_profile_id", "employee_persona"],
        ["id", "persona"],
        ondelete="CASCADE",
    )


def downgrade():
    op.drop_constraint("report_employee_persona", "reports", type_="foreignkey")
    op.drop_constraint("report_employee_only", "reports", type_="check")
    op.drop_column("reports", "employee_persona")
    op.drop_constraint("profile_id_persona", "demo_profiles", type_="unique")
    op.drop_constraint("profile_seeded_grade", "demo_profiles", type_="check")
    op.create_check_constraint(
        "profile_seeded_grade",
        "demo_profiles",
        "(persona = 'employee' AND grade = 'C') OR (persona = 'manager' AND grade IS NULL)",
    )
