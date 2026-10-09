"""Persist recruiter accounts, revocable sessions, conversations and owned jobs."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_recruiter_jobs"
down_revision = "0001_company_policy_knowledge"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("recruiters", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(256), nullable=False), sa.Column("active", sa.Boolean(), nullable=False))
    op.create_table("recruiter_sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("recruiter_id", sa.Uuid(), sa.ForeignKey("recruiters.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_recruiter_sessions_recruiter_id", "recruiter_sessions", ["recruiter_id"])
    op.create_table("recruiter_conversations", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recruiter_id", sa.Uuid(), sa.ForeignKey("recruiters.id"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False), sa.Column("state", JSONB, nullable=False))
    op.create_index("ix_recruiter_conversations_recruiter_id", "recruiter_conversations", ["recruiter_id"])
    op.create_table("recruiter_chat_turns", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("recruiter_conversations.id"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False), sa.Column("recruiter_message", sa.Text(), nullable=False),
        sa.Column("response", JSONB, nullable=False), sa.UniqueConstraint("conversation_id", "sequence", name="uq_chat_sequence"))
    op.create_index("ix_recruiter_chat_turns_conversation_id", "recruiter_chat_turns", ["conversation_id"])
    op.create_table("job_profiles", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recruiter_id", sa.Uuid(), sa.ForeignKey("recruiters.id"), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("recruiter_conversations.id"), unique=True),
        sa.Column("job_reference", sa.String(23), nullable=False, unique=True), sa.Column("job_title", sa.String(120), nullable=False),
        sa.Column("draft", JSONB), sa.Column("suggestions", JSONB, nullable=False), sa.Column("sources", JSONB, nullable=False),
        sa.Column("confirmed_snapshot", JSONB), sa.Column("revision", sa.Integer(), nullable=False))
    op.create_index("ix_job_profiles_recruiter_id", "job_profiles", ["recruiter_id"])


def downgrade():
    for table in ("job_profiles", "recruiter_chat_turns", "recruiter_conversations", "recruiter_sessions", "recruiters"):
        op.drop_table(table)
