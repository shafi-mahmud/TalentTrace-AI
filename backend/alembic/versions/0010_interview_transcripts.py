"""Storage foundation only; no live writer or retention/deletion automation."""
from alembic import op
import sqlalchemy as sa

revision = '0010_interview_transcripts'
down_revision = '0009_bulk_scheduling'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('interview_transcript_sessions',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('interview_id', sa.Uuid(), sa.ForeignKey('interview_schedules.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('recruiter_consented_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('candidate_consented_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('consent_version', sa.String(80), nullable=False),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('persistence_outcome', sa.String(16), nullable=False),
        sa.CheckConstraint("status IN ('active','completed','interrupted')", name='ck_transcript_session_status'),
        sa.CheckConstraint("persistence_outcome IN ('pending','saved','partial','failed')", name='ck_transcript_persistence'),
        sa.CheckConstraint("(status='active' AND ended_at IS NULL) OR (status<>'active' AND ended_at IS NOT NULL AND persistence_outcome<>'pending')", name='ck_transcript_lifecycle'),
        sa.CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='ck_transcript_end'),
        sa.CheckConstraint('recruiter_consented_at <= started_at AND candidate_consented_at <= started_at', name='ck_transcript_consent_time'),
        sa.CheckConstraint('length(consent_version) BETWEEN 1 AND 80', name='ck_transcript_consent_version'))
    op.create_index('ix_transcript_interview_start', 'interview_transcript_sessions', ['interview_id','started_at','id'])
    op.create_index('uq_transcript_active_interview', 'interview_transcript_sessions', ['interview_id'], unique=True, postgresql_where=sa.text("status='active'"))
    op.create_table('interview_transcript_turns',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('session_id', sa.Uuid(), sa.ForeignKey('interview_transcript_sessions.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('sequence', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(12), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('start_ms', sa.Integer(), nullable=False),
        sa.Column('end_ms', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('session_id','sequence', name='uq_transcript_turn_sequence'),
        sa.CheckConstraint('sequence > 0', name='ck_transcript_sequence'),
        sa.CheckConstraint("role IN ('recruiter','candidate')", name='ck_transcript_role'),
        sa.CheckConstraint('start_ms >= 0 AND end_ms >= start_ms', name='ck_transcript_turn_time'),
        sa.CheckConstraint('length(text) BETWEEN 1 AND 1000 AND length(btrim(text)) > 0', name='ck_transcript_text'))
    op.create_index('ix_transcript_turn_order','interview_transcript_turns',['session_id','start_ms','sequence','id'])


def downgrade():
    op.drop_table('interview_transcript_turns')
    op.drop_table('interview_transcript_sessions')
