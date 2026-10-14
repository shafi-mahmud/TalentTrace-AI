"""Synthetic candidate scheduling capabilities only."""
from alembic import op
import sqlalchemy as sa
revision='0006_self_scheduling'
down_revision='0005_interview_invitations'
branch_labels=None
depends_on=None

def upgrade():
 op.create_table('scheduling_invitations',
  sa.Column('id',sa.Uuid(),primary_key=True),
  sa.Column('recruiter_id',sa.Uuid(),sa.ForeignKey('recruiters.id'),nullable=False,index=True),
  sa.Column('job_id',sa.Uuid(),sa.ForeignKey('job_profiles.id'),nullable=False,index=True),
  sa.Column('batch_id',sa.Uuid(),nullable=False),sa.Column('upload_id',sa.Uuid(),nullable=False),
  sa.Column('criteria_revision',sa.Integer(),nullable=False),
  sa.Column('token_hash',sa.String(64),nullable=False,unique=True),
  sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
  sa.Column('unscored_confirmed',sa.Boolean(),nullable=False),sa.Column('revoked',sa.Boolean(),nullable=False),
  sa.Column('interview_id',sa.Uuid(),sa.ForeignKey('interview_schedules.id'),nullable=True))
def downgrade():op.drop_table('scheduling_invitations')
