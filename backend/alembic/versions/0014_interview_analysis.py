"""Privacy-bound durable analysis operations. No changes to existing interview rows."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0014_interview_analysis'
down_revision='0013_transcript_lifecycle'
branch_labels=None
depends_on=None


def upgrade():
    op.create_table('interview_analyses',
        sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('interview_id',sa.Uuid(),sa.ForeignKey('interview_schedules.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('recruiter_id',sa.Uuid(),sa.ForeignKey('recruiters.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('job_id',sa.Uuid(),sa.ForeignKey('job_profiles.id',ondelete='RESTRICT'),nullable=False),
        sa.Column('input_digest',sa.String(64),nullable=False),sa.Column('criteria_revision',sa.Integer(),nullable=False),
        sa.Column('rubric_version',sa.String(80),nullable=False),sa.Column('provider',sa.String(40),nullable=False),
        sa.Column('model',sa.String(200),nullable=False),sa.Column('corpus_version',sa.String(80),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),sa.Column('attempt',sa.Integer(),nullable=False),sa.Column('claim',sa.Uuid(),nullable=False),
        sa.Column('lease_expires_at',sa.DateTime(timezone=True),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.Column('error',sa.String(100)),sa.Column('result',JSONB),
        sa.UniqueConstraint('interview_id','input_digest','rubric_version','model','corpus_version',name='uq_interview_analysis_input'),
        sa.CheckConstraint("status IN ('running','completed','failed')",name='ck_analysis_status'),
        sa.CheckConstraint("(status='completed' AND result IS NOT NULL) OR (status<>'completed' AND result IS NULL)",name='ck_analysis_result'),
        sa.CheckConstraint('attempt > 0',name='ck_analysis_attempt'))
    op.create_index('ix_interview_analyses_interview_id','interview_analyses',['interview_id'])


def downgrade():op.drop_table('interview_analyses')
