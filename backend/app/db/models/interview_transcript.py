"""Private transcript foundation. No live caption writer is registered."""
from datetime import datetime
from uuid import UUID
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class InterviewTranscriptSession(Base):
    __tablename__ = 'interview_transcript_sessions'
    __table_args__ = (
        CheckConstraint("status IN ('active','completed','interrupted')", name='ck_transcript_session_status'),
        CheckConstraint("persistence_outcome IN ('pending','saved','partial','failed')", name='ck_transcript_persistence'),
        CheckConstraint("(status='active' AND ended_at IS NULL) OR (status<>'active' AND ended_at IS NOT NULL AND persistence_outcome<>'pending')", name='ck_transcript_lifecycle'),
        CheckConstraint('ended_at IS NULL OR ended_at >= started_at', name='ck_transcript_end'),
        CheckConstraint('recruiter_consented_at <= started_at AND candidate_consented_at <= started_at', name='ck_transcript_consent_time'),
        CheckConstraint('length(consent_version) BETWEEN 1 AND 80', name='ck_transcript_consent_version'),
        Index('ix_transcript_interview_start', 'interview_id', 'started_at', 'id'),
        Index('uq_transcript_active_interview', 'interview_id', unique=True, postgresql_where=text("status='active'")),
    )
    finalization_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    capture_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    id: Mapped[UUID] = mapped_column(primary_key=True)
    interview_id: Mapped[UUID] = mapped_column(ForeignKey('interview_schedules.id', ondelete='RESTRICT'))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    recruiter_consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    candidate_consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consent_version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(16))
    persistence_outcome: Mapped[str] = mapped_column(String(16))


class InterviewTranscriptTurn(Base):
    __tablename__ = 'interview_transcript_turns'
    __table_args__ = (
        UniqueConstraint('session_id', 'sequence', name='uq_transcript_turn_sequence'),
        CheckConstraint('sequence > 0', name='ck_transcript_sequence'),
        CheckConstraint("role IN ('recruiter','candidate')", name='ck_transcript_role'),
        CheckConstraint('start_ms >= 0 AND end_ms >= start_ms', name='ck_transcript_turn_time'),
        CheckConstraint('length(text) BETWEEN 1 AND 1000 AND length(btrim(text)) > 0', name='ck_transcript_text'),
        Index('ix_transcript_turn_order', 'session_id', 'start_ms', 'sequence', 'id'),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey('interview_transcript_sessions.id', ondelete='RESTRICT'))
    sequence: Mapped[int] = mapped_column(Integer)
    role: Mapped[str] = mapped_column(String(12))
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int] = mapped_column(Integer)
    end_ms: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TranscriptPrivacyAccess(Base):
    """Withdrawal-only capability, issued from an authenticated candidate session."""
    __tablename__ = 'transcript_privacy_access'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    interview_id: Mapped[UUID] = mapped_column(ForeignKey('interview_schedules.id', ondelete='RESTRICT'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
