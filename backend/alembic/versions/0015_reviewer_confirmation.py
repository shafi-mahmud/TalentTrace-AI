"""Bounded human confirmation, separate from F2/F5 output."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
revision = '0015_reviewer_confirmation'
down_revision = '0014_interview_analysis'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('reviewer_confirmations',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('job_id', sa.Uuid(), sa.ForeignKey('job_profiles.id', ondelete='CASCADE'), nullable=False),
        sa.Column('batch_id', sa.Uuid(), nullable=False), sa.Column('upload_id', sa.Uuid(), nullable=False),
        sa.Column('reviewer_id', sa.Uuid(), sa.ForeignKey('recruiters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('interview_id', sa.Uuid(), sa.ForeignKey('interview_schedules.id', ondelete='CASCADE')),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('criteria_revision', sa.Integer(), nullable=False),
        sa.Column('position', sa.String(20), nullable=False), sa.Column('scope', sa.String(20), nullable=False),
        sa.Column('requirement_ids', JSONB, nullable=False), sa.Column('evidence_references', JSONB, nullable=False),
        sa.Column('source_versions', JSONB, nullable=False), sa.Column('source_digest', sa.String(64), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('job_id','batch_id','upload_id',name='uq_confirmation_application'),
        sa.CheckConstraint('version > 0 AND criteria_revision > 0',name='ck_confirmation_version'),
        sa.CheckConstraint("position IN ('alignment','mixed','insufficient')",name='ck_confirmation_position'),
        sa.CheckConstraint("scope IN ('cv_only','cv_interview')",name='ck_confirmation_scope'),
        sa.CheckConstraint("(scope='cv_only' AND interview_id IS NULL) OR (scope='cv_interview' AND interview_id IS NOT NULL)",name='ck_confirmation_dependency'),
        sa.CheckConstraint("expires_at > confirmed_at AND expires_at <= confirmed_at + interval '30 days'",name='ck_confirmation_expiry'))
    for column in ('job_id','interview_id','expires_at'):
        op.create_index('ix_reviewer_confirmations_'+column,'reviewer_confirmations',[column])
    # Deferred: a same-transaction F2 replace must not count as application deletion.
    op.execute('''CREATE FUNCTION purge_orphan_confirmation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      DELETE FROM reviewer_confirmations c WHERE c.job_id=OLD.job_id AND c.batch_id=OLD.batch_id AND c.upload_id=OLD.upload_id
        AND NOT EXISTS (SELECT 1 FROM candidate_scores s WHERE s.job_id=c.job_id AND s.batch_id=c.batch_id AND s.upload_id=c.upload_id)
        AND NOT EXISTS (SELECT 1 FROM interview_schedules i WHERE i.job_id=c.job_id AND i.batch_id=c.batch_id AND i.upload_id=c.upload_id);
      RETURN NULL;
    END $$''')
    for table in ('candidate_scores','interview_schedules'):
        op.execute(f'CREATE CONSTRAINT TRIGGER purge_confirmation_{table} AFTER DELETE ON {table} DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION purge_orphan_confirmation()')


def downgrade():
    for table in ('candidate_scores','interview_schedules'):
        op.execute(f'DROP TRIGGER purge_confirmation_{table} ON {table}')
    op.execute('DROP FUNCTION purge_orphan_confirmation()')
    op.drop_table('reviewer_confirmations')
