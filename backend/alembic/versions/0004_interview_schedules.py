"""Recruiter-owned initial interview schedules; no external meeting provider."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0004_interview_schedules"
down_revision = "0003_candidate_scores"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("interview_schedules",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("recruiter_id", sa.Uuid(), sa.ForeignKey("recruiters.id"), nullable=False),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_profiles.id"), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False), sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("criteria_revision", sa.Integer(), nullable=False),
        sa.Column("scoring_version", sa.String(40), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(64), nullable=False),
        sa.Column("duration_minutes", sa.Integer(), nullable=False),
        sa.Column("unscored_confirmed", sa.Boolean(), nullable=False),
        sa.Column("screening_snapshot", JSONB, nullable=False),
        sa.UniqueConstraint("job_id", "batch_id", "upload_id", name="uq_initial_candidate_interview"),
        sa.CheckConstraint("criteria_revision >= 1", name="ck_interview_revision"),
        sa.CheckConstraint("duration_minutes BETWEEN 15 AND 180", name="ck_interview_duration"))
    op.create_index("ix_interview_schedules_job_id", "interview_schedules", ["job_id"])
    op.create_index("ix_interview_schedules_recruiter_id", "interview_schedules", ["recruiter_id"])


def downgrade():
    op.drop_table("interview_schedules")
