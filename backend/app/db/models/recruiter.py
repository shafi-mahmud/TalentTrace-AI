"""Relational recruiter ownership; validated JSON artifacts are not candidate records."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
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
