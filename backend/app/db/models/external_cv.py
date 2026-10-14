"""Intake ledger only; not a candidate profile or screening decision."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ExternalCvSubmissionRecord(Base):
    __tablename__ = "external_cv_submissions"
    __table_args__ = (
        UniqueConstraint("source_id", "external_submission_id", name="uq_external_cv_submission"),
        UniqueConstraint("batch_id", "upload_id", name="uq_external_cv_file"),
        CheckConstraint("status = 'pending_review'", name="ck_external_cv_status"),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760", name="ck_external_cv_size"),
        CheckConstraint("file_type IN ('pdf', 'docx')", name="ck_external_cv_type"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_profiles.id"), index=True)
    source_job_reference: Mapped[str] = mapped_column(String(23))
    source_id: Mapped[str] = mapped_column(String(64))
    external_submission_id: Mapped[str] = mapped_column(String(128))
    batch_id: Mapped[UUID] = mapped_column()
    upload_id: Mapped[UUID] = mapped_column()
    file_type: Mapped[str] = mapped_column(String(4))
    size_bytes: Mapped[int] = mapped_column()
    content_sha256: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending_review")
    application_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    contact_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    email_provenance: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email_collection_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    contact_validation_version: Mapped[int | None] = mapped_column(nullable=True)
    contact_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
