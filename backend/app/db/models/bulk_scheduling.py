"""Token/contact-free durable bulk approval and sanitized outcomes."""
from datetime import datetime,timezone
from uuid import UUID,uuid4
from sqlalchemy import String,DateTime,ForeignKey,Index,CheckConstraint,text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base
class BulkSchedulingOperation(Base):
    __tablename__='bulk_scheduling_operations'
    __table_args__=(Index('ix_bulk_scheduling_owner','recruiter_id','job_id'),Index('uq_bulk_scheduling_running_job','job_id',unique=True,postgresql_where=text("status='running'")),CheckConstraint("status IN ('preview','running','completed','partial')",name='ck_bulk_scheduling_status'),CheckConstraint('criteria_revision >= 1',name='ck_bulk_scheduling_revision'))
    id:Mapped[UUID]=mapped_column(primary_key=True,default=uuid4)
    recruiter_id:Mapped[UUID]=mapped_column(ForeignKey('recruiters.id'))
    job_id:Mapped[UUID]=mapped_column(ForeignKey('job_profiles.id'))
    criteria_revision:Mapped[int]=mapped_column()
    fingerprint:Mapped[str]=mapped_column(String(64))
    status:Mapped[str]=mapped_column(String(24),default='preview')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
    expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    preview:Mapped[dict]=mapped_column(JSONB)
    outcomes:Mapped[list]=mapped_column(JSONB,default=list)
