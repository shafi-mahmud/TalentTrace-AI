"""Recruiter-owned job application acknowledgements, independent of screening."""
from uuid import UUID
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class ApplicationView(Base):
    __tablename__ = "application_views"
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_profiles.id", ondelete="CASCADE"), primary_key=True)
    batch_id: Mapped[UUID] = mapped_column(primary_key=True)
    upload_id: Mapped[UUID] = mapped_column(primary_key=True)
