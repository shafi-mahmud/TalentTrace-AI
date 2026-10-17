"""One current human judgment; no quotations, names, CVs or free-text rationale."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ReviewerConfirmation(Base):
    __tablename__ = 'reviewer_confirmations'
    __table_args__ = (
        UniqueConstraint('job_id', 'batch_id', 'upload_id', name='uq_confirmation_application'),
        CheckConstraint('version > 0 AND criteria_revision > 0', name='ck_confirmation_version'),
        CheckConstraint("position IN ('alignment','mixed','insufficient')", name='ck_confirmation_position'),
        CheckConstraint("scope IN ('cv_only','cv_interview')", name='ck_confirmation_scope'),
        CheckConstraint("(scope='cv_only' AND interview_id IS NULL) OR (scope='cv_interview' AND interview_id IS NOT NULL)", name='ck_confirmation_dependency'),
        CheckConstraint("expires_at > confirmed_at AND expires_at <= confirmed_at + interval '30 days'", name='ck_confirmation_expiry'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey('job_profiles.id', ondelete='CASCADE'), index=True)
    batch_id: Mapped[UUID] = mapped_column()
    upload_id: Mapped[UUID] = mapped_column()
    reviewer_id: Mapped[UUID] = mapped_column(ForeignKey('recruiters.id', ondelete='CASCADE'))
    interview_id: Mapped[UUID | None] = mapped_column(ForeignKey('interview_schedules.id', ondelete='CASCADE'), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer)
    position: Mapped[str] = mapped_column(String(20))
    scope: Mapped[str] = mapped_column(String(20))
    criteria_revision: Mapped[int] = mapped_column(Integer)
    # Typed ID/code lists and canonical digests; no source text copied here.
    requirement_ids: Mapped[list] = mapped_column(JSONB)
    evidence_references: Mapped[list] = mapped_column(JSONB)
    source_versions: Mapped[dict] = mapped_column(JSONB)
    source_digest: Mapped[str] = mapped_column(String(64))
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
