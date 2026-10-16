"""Relational recruiter ownership; validated JSON artifacts are not candidate records."""
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, CheckConstraint, Float
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Recruiter(Base):
    __tablename__ = "recruiters"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    active: Mapped[bool] = mapped_column(default=True)


class RecruiterSession(Base):
    __tablename__ = "recruiter_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    recruiter_id: Mapped[UUID] = mapped_column(ForeignKey("recruiters.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class RecruiterConversation(Base):
    __tablename__ = "recruiter_conversations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recruiter_id: Mapped[UUID] = mapped_column(ForeignKey("recruiters.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Bounded, explicitly encoded orchestration state; never pickle or arbitrary classes.
    state: Mapped[dict] = mapped_column(JSONB, default=dict)


class ChatTurn(Base):
    __tablename__ = "recruiter_chat_turns"
    __table_args__ = (UniqueConstraint("conversation_id", "sequence", name="uq_chat_sequence"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(ForeignKey("recruiter_conversations.id"), index=True)
    sequence: Mapped[int] = mapped_column()
    recruiter_message: Mapped[str] = mapped_column(Text)
    response: Mapped[dict] = mapped_column(JSONB)


class JobProfile(Base):
    __tablename__ = "job_profiles"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recruiter_id: Mapped[UUID] = mapped_column(ForeignKey("recruiters.id"), index=True)
    conversation_id: Mapped[UUID | None] = mapped_column(ForeignKey("recruiter_conversations.id"), unique=True)
    job_reference: Mapped[str] = mapped_column(String(23), unique=True)
    job_title: Mapped[str] = mapped_column(String(120))
    draft: Mapped[dict | None] = mapped_column(JSONB)
    suggestions: Mapped[dict] = mapped_column(JSONB)
    sources: Mapped[list] = mapped_column(JSONB)
    # Exact validated approved API snapshot. Edits/revisions clear it atomically.
    confirmed_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    revision: Mapped[int] = mapped_column(default=1)
    scoring_weights: Mapped[dict] = mapped_column(JSONB, default=lambda: {"skill": 50, "experience": 30, "education": 20})


class CandidateScoreRecord(Base):
    __tablename__ = "candidate_scores"
    __table_args__ = (
        UniqueConstraint("job_id", "batch_id", "upload_id", "criteria_revision", "scoring_version", name="uq_candidate_score_version"),
        CheckConstraint("criteria_revision >= 1", name="ck_score_revision"),
        CheckConstraint("score IS NULL OR (score >= 0 AND score <= 100)", name="ck_score_range"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_profiles.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column(index=True)
    upload_id: Mapped[UUID] = mapped_column()
    criteria_revision: Mapped[int] = mapped_column()
    scoring_version: Mapped[str] = mapped_column(String(40))
    score: Mapped[float | None] = mapped_column(Float)
    payload: Mapped[dict] = mapped_column(JSONB)


class InterviewSchedule(Base):
    __tablename__ = "interview_schedules"
    __table_args__ = (
        UniqueConstraint("job_id", "batch_id", "upload_id", name="uq_initial_candidate_interview"),
        CheckConstraint("criteria_revision >= 1", name="ck_interview_revision"),
        CheckConstraint("duration_minutes BETWEEN 15 AND 180", name="ck_interview_duration"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recruiter_id: Mapped[UUID] = mapped_column(ForeignKey("recruiters.id"), index=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey("job_profiles.id"), index=True)
    batch_id: Mapped[UUID] = mapped_column()
    upload_id: Mapped[UUID] = mapped_column()
    criteria_revision: Mapped[int] = mapped_column()
    scoring_version: Mapped[str] = mapped_column(String(40))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(64))
    duration_minutes: Mapped[int] = mapped_column()
    unscored_confirmed: Mapped[bool] = mapped_column()
    # NULL is absence of withdrawal, never positive storage authorization.
    transcript_storage_revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_retention_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_deletion_status: Mapped[str] = mapped_column(String(12), default='none', server_default='none')
    transcript_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Immutable selection evidence survives replacement of F2 score rows on rerun.
    screening_snapshot: Mapped[dict] = mapped_column(JSONB)


class InterviewInvitation(Base):
    """One current single-use invitation; only bearer hashes are stored."""
    __tablename__ = "interview_invitations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    interview_id: Mapped[UUID] = mapped_column(ForeignKey("interview_schedules.id", ondelete="CASCADE"), unique=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(default=False)
    candidate_session_hash: Mapped[str | None] = mapped_column(String(64), unique=True)

class SchedulingInvitation(Base):
    """Separate scheduling capability; no raw bearer or candidate contact data."""
    __tablename__ = 'scheduling_invitations'
    recipient_email: Mapped[str | None] = mapped_column(String(254), nullable=True)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    recruiter_id: Mapped[UUID] = mapped_column(ForeignKey('recruiters.id'), index=True)
    job_id: Mapped[UUID] = mapped_column(ForeignKey('job_profiles.id'), index=True)
    batch_id: Mapped[UUID] = mapped_column()
    upload_id: Mapped[UUID] = mapped_column()
    criteria_revision: Mapped[int] = mapped_column()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    unscored_confirmed: Mapped[bool] = mapped_column(default=False)
    revoked: Mapped[bool] = mapped_column(default=False)
    interview_id: Mapped[UUID | None] = mapped_column(ForeignKey('interview_schedules.id'), nullable=True)

class InterviewEmailAttempt(Base):
    __tablename__ = 'interview_email_attempts'
    __table_args__ = (UniqueConstraint('scheduling_invitation_id', 'kind', name='uq_interview_email_kind'),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scheduling_invitation_id: Mapped[UUID] = mapped_column(ForeignKey('scheduling_invitations.id'), index=True)
    kind: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
