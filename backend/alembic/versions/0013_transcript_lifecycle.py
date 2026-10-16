"""Retention, deletion status and bounded transcript finalization metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '0013_transcript_lifecycle'
down_revision = '0012_transcript_privacy_guard'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('interview_schedules', sa.Column('transcript_retention_deadline', sa.DateTime(timezone=True)))
    op.add_column('interview_schedules', sa.Column('transcript_deletion_status', sa.String(12), nullable=False, server_default='none'))
    op.add_column('interview_schedules', sa.Column('transcript_deleted_at', sa.DateTime(timezone=True)))
    op.create_check_constraint('ck_transcript_deletion_status', 'interview_schedules', "transcript_deletion_status IN ('none','pending','failed','deleted')")
    op.add_column('interview_transcript_sessions', sa.Column('finalization_deadline', sa.DateTime(timezone=True)))
    op.add_column('interview_transcript_sessions', sa.Column('capture_summary', JSONB))
    # Conservative legacy fallback: capture creation precedes any stored text.
    op.execute("""UPDATE interview_schedules i SET transcript_retention_deadline =
        LEAST(s.started, i.scheduled_at + i.duration_minutes * interval '1 minute') + interval '30 days'
        FROM (SELECT interview_id, min(started_at) AS started FROM interview_transcript_sessions GROUP BY interview_id) s
        WHERE i.id=s.interview_id""")
    op.create_table('transcript_privacy_access',
        sa.Column('token_hash', sa.String(64), primary_key=True),
        sa.Column('interview_id', sa.Uuid(), sa.ForeignKey('interview_schedules.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_transcript_privacy_access_interview_id', 'transcript_privacy_access', ['interview_id'])


def downgrade():
    op.drop_table('transcript_privacy_access')
    op.drop_column('interview_transcript_sessions', 'capture_summary')
    op.drop_column('interview_transcript_sessions', 'finalization_deadline')
    op.drop_constraint('ck_transcript_deletion_status', 'interview_schedules', type_='check')
    for column in ('transcript_deleted_at','transcript_deletion_status','transcript_retention_deadline'):
        op.drop_column('interview_schedules', column)
