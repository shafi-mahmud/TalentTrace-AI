"""Durable cohort approval; no existing data changes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision='0009_bulk_scheduling'
down_revision='0008_application_bridge'
branch_labels=None
depends_on=None
def upgrade():
    op.create_table('bulk_scheduling_operations',sa.Column('id',sa.Uuid(),primary_key=True),
        sa.Column('recruiter_id',sa.Uuid(),sa.ForeignKey('recruiters.id'),nullable=False),
        sa.Column('job_id',sa.Uuid(),sa.ForeignKey('job_profiles.id'),nullable=False),
        sa.Column('criteria_revision',sa.Integer(),nullable=False),sa.Column('fingerprint',sa.String(64),nullable=False),
        sa.Column('status',sa.String(24),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),sa.Column('expires_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('preview',JSONB,nullable=False),sa.Column('outcomes',JSONB,nullable=False),
        sa.CheckConstraint("status IN ('preview','running','completed','partial')",name='ck_bulk_scheduling_status'),
        sa.CheckConstraint('criteria_revision >= 1',name='ck_bulk_scheduling_revision'))
    op.create_index('ix_bulk_scheduling_owner','bulk_scheduling_operations',['recruiter_id','job_id'])
    op.create_index('uq_bulk_scheduling_running_job','bulk_scheduling_operations',['job_id'],unique=True,postgresql_where=sa.text("status='running'"))
def downgrade():op.drop_table('bulk_scheduling_operations')
