"""Private policy questions and version-filtered embedding index; no extension activation."""

from alembic import op

revision = "0007_phase4_policy"
down_revision = "0006_phase3_categories"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE TABLE policy_chunks (
	id UUID NOT NULL,
	policy_version VARCHAR(100) NOT NULL,
	config_id VARCHAR(100) NOT NULL,
	clause_id VARCHAR(32) NOT NULL,
	source_hash VARCHAR(64) NOT NULL,
	text_hash VARCHAR(64) NOT NULL,
	embedding TEXT NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT policy_chunk_once UNIQUE (policy_version, config_id, clause_id),
	FOREIGN KEY(policy_version) REFERENCES meal_policy_versions (id)
)
""")
    op.execute("""
CREATE TABLE policy_questions (
	id UUID NOT NULL,
	session_id UUID NOT NULL,
	report_id UUID NOT NULL,
	expense_id UUID,
	expense_revision_id UUID,
	request_id UUID NOT NULL,
	question VARCHAR(800) NOT NULL,
	policy_version VARCHAR(100) NOT NULL,
	state VARCHAR(16) NOT NULL,
	mode VARCHAR(16) NOT NULL,
	attempts INTEGER NOT NULL,
	lease_token UUID,
	lease_until TIMESTAMP WITH TIME ZONE,
	result JSON,
	failure_code VARCHAR(40),
	created_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
        CONSTRAINT policy_question_report_owner FOREIGN KEY(session_id, report_id) REFERENCES
        reports (session_id, id) ON DELETE CASCADE,
        CONSTRAINT policy_question_expense_owner FOREIGN KEY(session_id, expense_id) REFERENCES
        expenses (session_id, id) ON DELETE CASCADE,
        CONSTRAINT policy_question_revision FOREIGN KEY(expense_id, expense_revision_id)
        REFERENCES expense_revisions (expense_id, id) ON DELETE CASCADE,
	CONSTRAINT policy_question_attempts CHECK (attempts BETWEEN 0 AND 3),
        CONSTRAINT policy_question_lease CHECK ((state = 'processing' AND lease_token IS NOT
        NULL AND lease_until IS NOT NULL) OR (state != 'processing' AND lease_token IS NULL AND
        lease_until IS NULL)),
	CONSTRAINT policy_question_request_once UNIQUE (session_id, request_id),
        CONSTRAINT policy_question_state CHECK (state IN
        ('queued','processing','complete','failed','stale')),
	CONSTRAINT policy_question_mode CHECK (mode IN ('rag','fullContext')),
	FOREIGN KEY(expense_id) REFERENCES expenses (id) ON DELETE CASCADE,
	FOREIGN KEY(policy_version) REFERENCES meal_policy_versions (id)
)
""")


def downgrade():
    op.drop_table("policy_questions")
    op.drop_table("policy_chunks")
