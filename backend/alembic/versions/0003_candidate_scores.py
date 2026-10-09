"""Reviewed scoring weights and owner-linked evidence score records."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = "0003_candidate_scores"
down_revision = "0002_recruiter_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("job_profiles", sa.Column("scoring_weights", JSONB, nullable=False,
        server_default=sa.text("'{\"skill\":50,\"experience\":30,\"education\":20}'::jsonb")))
    op.create_check_constraint("ck_job_scoring_weights", "job_profiles",
        "jsonb_typeof(scoring_weights) = 'object' AND scoring_weights ?& ARRAY['skill','experience','education'] "
        "AND (scoring_weights - 'skill' - 'experience' - 'education') = '{}'::jsonb "
        "AND jsonb_typeof(scoring_weights->'skill') = 'number' "
        "AND jsonb_typeof(scoring_weights->'experience') = 'number' "
        "AND jsonb_typeof(scoring_weights->'education') = 'number' "
        "AND (scoring_weights->>'skill') ~ '^(100|[1-9]?[0-9])$' "
        "AND (scoring_weights->>'experience') ~ '^(100|[1-9]?[0-9])$' "
        "AND (scoring_weights->>'education') ~ '^(100|[1-9]?[0-9])$' "
        "AND (scoring_weights->>'skill')::int + (scoring_weights->>'experience')::int + (scoring_weights->>'education')::int = 100")
    op.create_table("candidate_scores", sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_profiles.id"), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False), sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("criteria_revision", sa.Integer(), nullable=False), sa.Column("scoring_version", sa.String(40), nullable=False),
        sa.Column("score", sa.Float()), sa.Column("payload", JSONB, nullable=False),
        sa.UniqueConstraint("job_id", "batch_id", "upload_id", "criteria_revision", "scoring_version", name="uq_candidate_score_version"),
        sa.CheckConstraint("criteria_revision >= 1", name="ck_score_revision"),
        sa.CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_score_range"))
    op.create_index("ix_candidate_scores_job_id", "candidate_scores", ["job_id"])
    op.create_index("ix_candidate_scores_batch_id", "candidate_scores", ["batch_id"])


def downgrade():
    op.drop_table("candidate_scores")
    op.drop_constraint("ck_job_scoring_weights", "job_profiles", type_="check")
    op.drop_column("job_profiles", "scoring_weights")
