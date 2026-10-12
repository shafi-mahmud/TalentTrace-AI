"""Hashed single-use interview invitations and reconnect sessions."""
from alembic import op
import sqlalchemy as sa

revision = "0005_interview_invitations"
down_revision = "0004_interview_schedules"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("interview_invitations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("interview_id", sa.Uuid(), sa.ForeignKey("interview_schedules.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("candidate_session_hash", sa.String(64), nullable=True, unique=True))


def downgrade():
    op.drop_table("interview_invitations")
