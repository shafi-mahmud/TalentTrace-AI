"""Application acknowledgement state only; existing candidates are untouched."""
from alembic import op
import sqlalchemy as sa

revision = "0011_application_views"
down_revision = "0010_interview_transcripts"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("application_views",
        sa.Column("job_id", sa.Uuid(), sa.ForeignKey("job_profiles.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("batch_id", sa.Uuid(), primary_key=True),
        sa.Column("upload_id", sa.Uuid(), primary_key=True))


def downgrade():
    op.drop_table("application_views")
