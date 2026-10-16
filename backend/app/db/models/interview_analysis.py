"""Derived text has the same interview privacy/retention boundary as source turns."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint,ForeignKey,String,DateTime,Integer,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped,mapped_column
from app.db.base import Base


class InterviewAnalysis(Base):
    __tablename__='interview_analyses'
    __table_args__=(
        UniqueConstraint('interview_id','input_digest','rubric_version','model','corpus_version',name='uq_interview_analysis_input'),
        CheckConstraint("status IN ('running','completed','failed')",name='ck_analysis_status'),
        CheckConstraint("(status='completed' AND result IS NOT NULL) OR (status<>'completed' AND result IS NULL)",name='ck_analysis_result'),
        CheckConstraint('attempt > 0',name='ck_analysis_attempt'),)
    id:Mapped[UUID]=mapped_column(primary_key=True)
    interview_id:Mapped[UUID]=mapped_column(ForeignKey('interview_schedules.id',ondelete='RESTRICT'),index=True)
    recruiter_id:Mapped[UUID]=mapped_column(ForeignKey('recruiters.id',ondelete='RESTRICT'))
    job_id:Mapped[UUID]=mapped_column(ForeignKey('job_profiles.id',ondelete='RESTRICT'))
    input_digest:Mapped[str]=mapped_column(String(64))
    criteria_revision:Mapped[int]=mapped_column(Integer)
    rubric_version:Mapped[str]=mapped_column(String(80))
    provider:Mapped[str]=mapped_column(String(40))
    model:Mapped[str]=mapped_column(String(200))
    corpus_version:Mapped[str]=mapped_column(String(80))
    status:Mapped[str]=mapped_column(String(16))
    attempt:Mapped[int]=mapped_column(Integer)
    claim:Mapped[UUID]=mapped_column()
    lease_expires_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True))
    error:Mapped[str|None]=mapped_column(String(100),nullable=True)
    result:Mapped[dict|None]=mapped_column(JSONB(none_as_null=True),nullable=True)
