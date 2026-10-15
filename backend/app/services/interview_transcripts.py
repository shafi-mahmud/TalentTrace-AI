"""Internal, owner-scoped persistence. No caption hook, HTTP route or retry loop."""
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import asyncio
import hashlib
import hmac
import secrets
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, or_, func, text
from sqlalchemy.exc import SQLAlchemyError
from app.core.auth import current_recruiter, protect_mutation
from app.api.routers.interview_access import candidate_session, owned_schedule
from app.db.models.recruiter import InterviewSchedule, InterviewInvitation, JobProfile, Recruiter
from app.db.models.interview_transcript import InterviewTranscriptSession, InterviewTranscriptTurn
from app.schemas.interview_transcript import FinalTranscriptEvent
from app.services.livekit_interview import join_window


class TranscriptError(ValueError):
    """Fixed public code only; never include a transcript or underlying DB error."""
    def __init__(self, code, *, outcome_uncertain=False):
        super().__init__(code)
        self.code, self.outcome_uncertain = code, outcome_uncertain


def utc_now():
    return datetime.now(timezone.utc)


@asynccontextmanager
async def transaction(factory):
    committing = False
    try:
        async with asyncio.timeout(5):
            async with factory() as db:
                async with db.begin():
                    await db.execute(text("SET LOCAL statement_timeout='3000ms'"))
                    await db.execute(text("SET LOCAL lock_timeout='1000ms'"))
                    yield db
                    await db.flush()
                    committing = True
    except (SQLAlchemyError, TimeoutError):
        # A lost COMMIT acknowledgement cannot honestly be called a rollback.
        raise TranscriptError('transcript_storage_unavailable', outcome_uncertain=committing) from None


@dataclass(frozen=True, repr=False)
class _StorageConsent:
    capture_id: UUID
    interview_id: UUID
    role: str
    actor_id: UUID
    accepted_at: datetime
    version: str
    signature: bytes


class StorageConsentAuthority:
    """Only an authenticated participant's explicit storage action issues a receipt.

    No live route calls this class yet. The future consent route must send the
    version header only after separate storage disclosure/acceptance. Ordinary
    login, live-caption consent, booleans and serialized receipts are insufficient.
    """
    def __init__(self, factory, *, version, clock=utc_now):
        if not isinstance(version, str) or not 1 <= len(version) <= 80 or not version.isascii():
            raise TranscriptError('invalid_consent_version')
        self.factory, self.version, self.clock = factory, version, clock
        self._key = secrets.token_bytes(32)

    def _signature(self, capture, interview, role, actor, accepted, version):
        message = '|'.join(map(str, (capture, interview, role, actor, accepted.isoformat(), version)))
        return hmac.new(self._key, message.encode(), hashlib.sha256).digest()

    async def accept(self, request, *, capture_id, interview_id, job_id=None):
        if (request.method != 'POST' or request.headers.get('x-talenttrace-storage-consent') != self.version
                or not isinstance(capture_id, UUID) or not isinstance(interview_id, UUID)):
            raise TranscriptError('storage_consent_not_verified')
        try:
            async with transaction(self.factory) as db:
                if job_id is not None:
                    user = await current_recruiter(request, db)
                    interview = await owned_schedule(db, user, job_id, interview_id)
                    role, actor = 'recruiter', user.id
                else:
                    await protect_mutation(request)
                    invitation, interview = await candidate_session(request, db)
                    if interview.id != interview_id:
                        raise TranscriptError('storage_consent_not_verified')
                    role, actor = 'candidate', invitation.id
                join_window(interview)
            accepted = self.clock().astimezone(timezone.utc)
            return _StorageConsent(capture_id, interview_id, role, actor, accepted, self.version,
                self._signature(capture_id, interview_id, role, actor, accepted, self.version))
        except (HTTPException, ValueError) as error:
            if isinstance(error, TranscriptError):
                raise
            raise TranscriptError('storage_consent_not_verified') from None

    def verify(self, receipt, *, capture_id, interview_id, role):
        if type(receipt) is not _StorageConsent:
            raise TranscriptError('storage_consent_not_verified')
        expected = self._signature(receipt.capture_id, receipt.interview_id, receipt.role,
            receipt.actor_id, receipt.accepted_at, receipt.version)
        age = (self.clock() - receipt.accepted_at).total_seconds()
        if (not hmac.compare_digest(expected, receipt.signature) or not 0 <= age <= 300
                or (receipt.capture_id, receipt.interview_id, receipt.role, receipt.version) !=
                (capture_id, interview_id, role, self.version)):
            raise TranscriptError('storage_consent_not_verified')
        return receipt


class TranscriptPersistenceService:
    def __init__(self, factory, consent_authority, *, clock=utc_now):
        self.factory, self.authority, self.clock = factory, consent_authority, clock

    async def _owned(self, db, owner, interview_id, *, current=False, lock=False):
        query = select(InterviewSchedule, JobProfile).join(JobProfile,
            JobProfile.id == InterviewSchedule.job_id).join(Recruiter,
            Recruiter.id == InterviewSchedule.recruiter_id).where(
            InterviewSchedule.id == interview_id, InterviewSchedule.recruiter_id == owner,
            JobProfile.recruiter_id == owner, Recruiter.active.is_(True))
        if lock:
            query = query.with_for_update(of=InterviewSchedule)
        pair = (await db.execute(query)).first()
        if pair is None:
            raise TranscriptError('owned_interview_not_found')
        interview, job = pair
        if current:
            if job.confirmed_snapshot is None or job.revision != interview.criteria_revision:
                raise TranscriptError('interview_revision_changed')
            try:
                join_window(interview, self.clock())
            except ValueError:
                raise TranscriptError('interview_window_closed') from None
        return interview

    async def create_session(self, owner, interview_id, capture_id, recruiter_consent, candidate_consent):
        if not isinstance(capture_id, UUID):
            raise TranscriptError('invalid_capture_identity')
        recruiter = self.authority.verify(recruiter_consent, capture_id=capture_id, interview_id=interview_id, role='recruiter')
        candidate = self.authority.verify(candidate_consent, capture_id=capture_id, interview_id=interview_id, role='candidate')
        if recruiter.actor_id != owner:
            raise TranscriptError('storage_consent_not_verified')
        async with transaction(self.factory) as db:
            await self._owned(db, owner, interview_id, current=True, lock=True)
            invitation = await db.scalar(select(InterviewInvitation).where(
                InterviewInvitation.id == candidate.actor_id, InterviewInvitation.interview_id == interview_id,
                InterviewInvitation.revoked.is_(False), InterviewInvitation.expires_at > self.clock(),
                InterviewInvitation.candidate_session_hash.is_not(None)))
            if invitation is None:
                raise TranscriptError('storage_consent_not_verified')
            row = await db.get(InterviewTranscriptSession, capture_id)
            if row is not None:
                if (row.interview_id, row.recruiter_consented_at, row.candidate_consented_at, row.consent_version) != (
                        interview_id, recruiter.accepted_at, candidate.accepted_at, self.authority.version):
                    raise TranscriptError('transcript_identity_conflict')
                return row
            active = await db.scalar(select(InterviewTranscriptSession.id).where(
                InterviewTranscriptSession.interview_id == interview_id, InterviewTranscriptSession.status == 'active'))
            if active:
                raise TranscriptError('capture_already_active')
            row = InterviewTranscriptSession(id=capture_id, interview_id=interview_id, started_at=self.clock(),
                ended_at=None, recruiter_consented_at=recruiter.accepted_at, candidate_consented_at=candidate.accepted_at,
                consent_version=self.authority.version, status='active', persistence_outcome='pending')
            db.add(row)
        return row

    async def append_final(self, owner, event):
        if type(event) is not FinalTranscriptEvent:
            raise TranscriptError('invalid_final_event')
        # Revalidate even an object constructed using Pydantic's unchecked constructor.
        event = FinalTranscriptEvent.model_validate(event.model_dump())
        async with transaction(self.factory) as db:
            capture = await db.scalar(select(InterviewTranscriptSession).join(InterviewSchedule).where(
                InterviewTranscriptSession.id == event.session_id, InterviewSchedule.recruiter_id == owner)
                .with_for_update(of=InterviewTranscriptSession))
            if capture is None:
                raise TranscriptError('capture_not_found')
            await self._owned(db, owner, capture.interview_id)
            existing = (await db.scalars(select(InterviewTranscriptTurn).where(or_(
                InterviewTranscriptTurn.id == event.id,
                (InterviewTranscriptTurn.session_id == event.session_id) & (InterviewTranscriptTurn.sequence == event.sequence))))).all()
            fields = ('id','session_id','sequence','role','text','start_ms','end_ms')
            if existing:
                if len(existing) != 1 or any(getattr(existing[0], key) != getattr(event, key) for key in fields):
                    raise TranscriptError('transcript_identity_conflict')
                return existing[0]
            if capture.status != 'active':
                raise TranscriptError('capture_closed')
            await self._owned(db, owner, capture.interview_id, current=True)
            if not capture.recruiter_consented_at or not capture.candidate_consented_at:
                raise TranscriptError('storage_consent_not_verified')
            now = self.clock()
            if event.end_ms > int((now - capture.started_at).total_seconds() * 1000):
                raise TranscriptError('invalid_recognition_time')
            row = InterviewTranscriptTurn(**{key:getattr(event,key) for key in fields}, created_at=now)
            db.add(row)
            capture.persistence_outcome = 'saved'
        return row

    async def finish_session(self, owner, capture_id, *, completed, persistence_failed=False):
        if type(completed) is not bool or type(persistence_failed) is not bool:
            raise TranscriptError('invalid_session_outcome')
        async with transaction(self.factory) as db:
            capture = await db.scalar(select(InterviewTranscriptSession).join(InterviewSchedule).where(
                InterviewTranscriptSession.id == capture_id, InterviewSchedule.recruiter_id == owner)
                .with_for_update(of=InterviewTranscriptSession))
            if capture is None:
                raise TranscriptError('capture_not_found')
            await self._owned(db, owner, capture.interview_id)
            count = await db.scalar(select(func.count()).select_from(InterviewTranscriptTurn).where(
                InterviewTranscriptTurn.session_id == capture_id))
            outcome = 'saved' if completed and not persistence_failed else ('partial' if count else 'failed')
            status = 'completed' if completed else 'interrupted'
            if capture.status != 'active':
                if (capture.status, capture.persistence_outcome) != (status, outcome):
                    raise TranscriptError('session_outcome_conflict')
                return capture
            capture.status, capture.persistence_outcome, capture.ended_at = status, outcome, self.clock()
        return capture

    async def list_turns(self, owner, interview_id, *, limit=100, offset=0):
        """Internal bounded read, not an HTTP API. Stable order for a fixed dataset."""
        if type(limit) is not int or not 1 <= limit <= 200 or type(offset) is not int or not 0 <= offset <= 100000:
            raise TranscriptError('invalid_transcript_page')
        async with transaction(self.factory) as db:
            await self._owned(db, owner, interview_id)
            return list((await db.scalars(select(InterviewTranscriptTurn).join(InterviewTranscriptSession).where(
                InterviewTranscriptSession.interview_id == interview_id).order_by(
                InterviewTranscriptSession.started_at, InterviewTranscriptSession.id,
                InterviewTranscriptTurn.start_ms, InterviewTranscriptTurn.sequence, InterviewTranscriptTurn.id)
                .limit(limit).offset(offset))).all())
