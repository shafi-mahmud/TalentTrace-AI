"""Private recipient binding and token-free synchronous delivery attempts."""
from alembic import op
import sqlalchemy as sa
revision='0007_interview_email'
down_revision='0006_self_scheduling'
branch_labels=None
depends_on=None
def upgrade():
 op.add_column('scheduling_invitations',sa.Column('recipient_email',sa.String(254),nullable=True))
 op.create_table('interview_email_attempts',sa.Column('id',sa.Uuid(),primary_key=True),
  sa.Column('scheduling_invitation_id',sa.Uuid(),sa.ForeignKey('scheduling_invitations.id'),nullable=False,index=True),
  sa.Column('kind',sa.String(20),nullable=False),sa.Column('status',sa.String(20),nullable=False),
  sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
  sa.UniqueConstraint('scheduling_invitation_id','kind',name='uq_interview_email_kind'))
def downgrade():
 op.drop_table('interview_email_attempts');op.drop_column('scheduling_invitations','recipient_email')
