"""Durable interview-wide storage withdrawal; no transcript writer activation."""
from alembic import op
import sqlalchemy as sa

revision = '0012_transcript_privacy_guard'
down_revision = '0011_application_views'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('interview_schedules', sa.Column(
        'transcript_storage_revoked_at', sa.DateTime(timezone=True), nullable=True))


def downgrade():
    # Schema rollback loses withdrawal history. Never use against an activated
    # storage system without a separately reviewed data/privacy recovery plan.
    op.drop_column('interview_schedules', 'transcript_storage_revoked_at')
