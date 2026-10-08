"""Evidence-backed category assessment; no policy activation in a migration."""

from alembic import op

revision = "0006_phase3_categories"
down_revision = "0005_phase2_meals"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("expense_state", "expenses", type_="check")
    op.create_check_constraint(
        "expense_state",
        "expenses",
        "state IN ('queued','processing','needs_information',"
        "'review','failed','unsupported',"
        "'unreadable','policy_inactive','conversion_pending','excluded','conflict',"
        "'noncompliant','profile_incomplete')",
    )


def downgrade():
    op.execute(
        "UPDATE expenses SET state = 'needs_information', calculation = NULL "
        "WHERE state IN ('noncompliant','profile_incomplete')"
    )
    op.drop_constraint("expense_state", "expenses", type_="check")
    op.create_check_constraint(
        "expense_state",
        "expenses",
        "state IN ('queued','processing','needs_information',"
        "'review','failed','unsupported',"
        "'unreadable','policy_inactive','conversion_pending','excluded','conflict')",
    )
