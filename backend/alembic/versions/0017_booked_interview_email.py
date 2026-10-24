"""Separate recruiter-booked appointment email reservation."""
from alembic import op
import sqlalchemy as sa
revision = '0017_booked_interview_email'
down_revision = '0016_submission_deletion'
branch_labels = depends_on = None


def upgrade():
    op.create_table('booked_interview_email_attempts',
        sa.Column('interview_id', sa.Uuid(), sa.ForeignKey('interview_schedules.id'), primary_key=True),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("status IN ('sending','accepted','failed','uncertain')", name='ck_booked_email_status'))


def downgrade():
    # Dropping reservations would permit resend after an uncertain/accepted send.
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM booked_interview_email_attempts) THEN RAISE EXCEPTION 'booked_email_journal_not_empty'; END IF; END $$")
    op.drop_table('booked_interview_email_attempts')
