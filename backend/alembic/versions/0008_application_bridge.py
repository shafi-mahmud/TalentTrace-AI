"""Minimal external intake ledger; no screening or notification triggers."""
from alembic import op
import sqlalchemy as sa

revision = "0008_application_bridge"
down_revision = "0007_interview_email"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("external_cv_submissions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_profiles.id"), nullable=False),
        sa.Column("source_job_reference", sa.String(23), nullable=False),
        sa.Column("application_email", sa.String(254)),
        sa.Column("contact_status", sa.String(16)),
        sa.Column("email_provenance", sa.String(40)),
        sa.Column("email_collection_type", sa.String(32)),
        sa.Column("contact_validation_version", sa.Integer()),
        sa.Column("contact_updated_at", sa.DateTime(timezone=True)),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("external_submission_id", sa.String(128), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("upload_id", sa.Uuid(), nullable=False),
        sa.Column("file_type", sa.String(4), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("source_id", "external_submission_id", name="uq_external_cv_submission"),
        sa.UniqueConstraint("batch_id", "upload_id", name="uq_external_cv_file"),
        sa.CheckConstraint("status = 'pending_review'", name="ck_external_cv_status"),
        sa.CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_external_cv_size"),
        sa.CheckConstraint("file_type IN ('pdf', 'docx')", name="ck_external_cv_type"))
    op.create_index("ix_external_cv_submissions_job_id", "external_cv_submissions", ["job_id"])


def downgrade():
    op.drop_table("external_cv_submissions")
