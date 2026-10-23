"""Minimal retry journal and external-submission replay fence; no source text."""
from alembic import op
import sqlalchemy as sa
revision = '0016_submission_deletion'
down_revision = '0015_reviewer_confirmation'
branch_labels = depends_on = None


def upgrade():
    op.create_table('submission_deletions',
        sa.Column('job_id', sa.Uuid(), nullable=False),
        sa.Column('batch_id', sa.Uuid(), nullable=False),
        sa.Column('upload_id', sa.Uuid(), nullable=False),
        sa.Column('recruiter_id', sa.Uuid(), nullable=False),
        sa.Column('source_digest', sa.String(64), nullable=False, unique=True),
        sa.Column('plan_digest', sa.String(64), nullable=False),
        sa.Column('file_digest', sa.String(64), nullable=False),
        sa.Column('job_reference', sa.String(23), nullable=False),
        sa.Column('file_type', sa.String(4), nullable=False),
        sa.Column('state', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('job_id', 'batch_id', 'upload_id'),
        sa.CheckConstraint("state IN ('file_pending','complete')", name='ck_submission_deletion_state'),
        sa.CheckConstraint("file_type IN ('pdf','docx')", name='ck_submission_deletion_type'),
        sa.CheckConstraint("source_digest ~ '^[a-f0-9]{64}$' AND file_digest ~ '^[a-f0-9]{64}$'", name='ck_submission_deletion_digest'))
    # PostgreSQL builtin sha256(bytea); no new extension. Same byte encoding as Python.
    op.execute("""CREATE FUNCTION prevent_deleted_submission() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF EXISTS (SELECT 1 FROM submission_deletions WHERE source_digest=
          encode(sha256(convert_to(NEW.source_id,'UTF8') || decode('00','hex') ||
                        convert_to(NEW.external_submission_id,'UTF8')),'hex')) THEN
        RAISE EXCEPTION 'external_submission_deleted' USING ERRCODE='23514';
      END IF;
      RETURN NEW;
    END $$""")
    op.execute('CREATE TRIGGER prevent_deleted_submission BEFORE INSERT OR UPDATE ON external_cv_submissions FOR EACH ROW EXECUTE FUNCTION prevent_deleted_submission()')


def downgrade():
    # Do not silently discard a replay fence or incomplete cleanup journal.
    op.execute("DO $$ BEGIN IF EXISTS(SELECT 1 FROM submission_deletions) THEN RAISE EXCEPTION 'deletion_journal_not_empty'; END IF; END $$")
    op.execute('DROP TRIGGER prevent_deleted_submission ON external_cv_submissions')
    op.execute('DROP FUNCTION prevent_deleted_submission()')
    op.drop_table('submission_deletions')
