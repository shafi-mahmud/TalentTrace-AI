"""Optional storage-consent integration; live activation is explicitly configured.

PostgreSQL provides the revocation fence. Pending receipts remain process-local.
PostgreSQL privacy checks remain authoritative when runtime storage is enabled.
"""
import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.services.interview_transcripts import TranscriptError, transaction
from app.db.models.interview_transcript import InterviewTranscriptSession


CONSENT_VERSION = 'optional-transcript-storage-v1'
CONSENT_WORDING = """Optional Interview Transcript Storage Consent

I agree to the storage of a text transcript of this interview for review by the authorized recruiter.

I understand that:
- Both participants must independently consent before transcript storage begins.
- Declining consent will not prevent temporary live captions.
- This consent does not authorize audio or video recording.
- Stored transcripts will be retained for no more than 30 days after the interview, unless deleted earlier.
- Either participant may withdraw consent and request deletion of the stored transcript.
- AI-assisted evaluation and any disclosure to external AI providers will require separate, clear information about how the transcript is used.

I understand that speech-to-text transcription may contain errors.

I agree to optional transcript storage."""


@dataclass(repr=False)
class _Pending:
    capture_id: UUID
    owner: UUID
    receipts: dict = field(default_factory=dict)
    status: str = 'awaiting_consent'
    session_may_exist: bool = False
    closure_pending: bool = False
    withdrawal_committed: bool = False


class TranscriptConsentCoordinator:
    """Single-process pending-consent orchestration for the single-room caption worker.

    Receipts stay private in RAM. Authenticated routes call prepare and decide;
    durable privacy checks protect every storage operation independently.
    One capture per interview per coordinator lifetime; no reset after revocation.
    """
    def __init__(self, authority, persistence, *, enabled=False):
        if authority.version != CONSENT_VERSION or persistence.authority is not authority:
            raise TranscriptError('invalid_consent_version')
        self.authority, self.persistence = authority, persistence
        self.enabled = enabled
        self._entries = {}
        self._lock = asyncio.Lock()

    def _view(self, entry):
        return {'capture_id': entry.capture_id, 'consent_version': CONSENT_VERSION,
                'status': entry.status, 'transcript_saved': False,
                'transcript_writing_enabled': self.enabled,
                'durable_revocation_enforced': True,
                'withdrawal_committed': entry.withdrawal_committed,
                'session_closure_pending': entry.closure_pending,
                'deletion_verified': False}

    async def prepare(self, request, *, interview_id, job_id=None):
        async with self._lock:
            _, _, owner = await self.authority.participant(request, interview_id=interview_id, job_id=job_id)
            entry = self._entries.get(interview_id)
            if entry is None:
                if len(self._entries) >= 100:
                    raise TranscriptError('storage_consent_capacity_unavailable')
                entry = self._entries[interview_id] = _Pending(uuid4(), owner)
            if self.enabled and not entry.session_may_exist and entry.receipts and any(
                    (self.authority.clock()-receipt.accepted_at).total_seconds()>300 for receipt in entry.receipts.values()):
                # Explicitly reviewing again starts a fresh two-party handshake,
                # never silently renew an expired acceptance during decide().
                entry = self._entries[interview_id] = _Pending(uuid4(),owner)
            if self.enabled and entry.status not in ('withdrawn','declined') and entry.session_may_exist:
                async with transaction(self.persistence.factory) as db:
                    capture = await db.get(InterviewTranscriptSession,entry.capture_id)
                    if capture is None or capture.status != 'active':
                        entry = self._entries[interview_id] = _Pending(uuid4(),owner)
            if entry.owner != owner:
                raise TranscriptError('storage_consent_not_verified')
            return {**self._view(entry), 'wording': CONSENT_WORDING}

    async def decide(self, request, *, interview_id, capture_id, decision, job_id=None):
        if decision not in ('accept', 'decline', 'withdraw'):
            raise TranscriptError('invalid_storage_decision')
        # This lock only protects local pending receipts. Database interview-row
        # locks serialize privacy decisions with all persistence operations.
        async with self._lock:
            if decision in ('decline', 'withdraw'):
                # No local entry is required: another process or a restarted
                # service must still be able to withdraw interview-wide consent.
                owner = await self.authority.withdraw(request, interview_id=interview_id, job_id=job_id)
                self.authority.revoke(interview_id)
                entry = self._entries.get(interview_id)
                if entry is None:
                    # No capture identity is trusted for cleanup on this process.
                    # Report cleanup pending; durable revocation is already done.
                    entry = _Pending(capture_id, owner, closure_pending=True)
                    entry.status = 'withdrawn' if decision == 'withdraw' else 'declined'
                    entry.withdrawal_committed = True
                    return self._view(entry)
                entry.receipts.clear()
                entry.closure_pending = entry.session_may_exist
                entry.status = 'withdrawn' if decision == 'withdraw' else 'declined'
                entry.withdrawal_committed = True
                if entry.closure_pending:
                    await self.persistence.finish_session(owner, entry.capture_id, completed=False)
                    entry.session_may_exist = False
                    entry.closure_pending = False
                return self._view(entry)
            role, actor, owner = await self.authority.participant(request, interview_id=interview_id, job_id=job_id)
            entry = self._entries.get(interview_id)
            if entry is None or entry.capture_id != capture_id or entry.owner != owner:
                raise TranscriptError('storage_consent_not_verified')
            if entry.status in ('declined', 'withdrawn'):
                raise TranscriptError('storage_authorization_revoked')
            # Reauthenticate every duplicate as well; reuse its original receipt
            # so timestamps and create_session idempotency remain stable.
            new = await self.authority.accept(request, capture_id=capture_id,
                interview_id=interview_id, job_id=job_id)
            old = entry.receipts.get(role)
            if old is not None and old.actor_id != actor:
                raise TranscriptError('storage_consent_not_verified')
            receipt = old or new
            self.authority.verify(receipt, capture_id=capture_id, interview_id=interview_id, role=role)
            entry.receipts[role] = receipt
            if set(entry.receipts) == {'recruiter', 'candidate'}:
                for participant, stored in entry.receipts.items():
                    self.authority.verify(stored, capture_id=capture_id,
                        interview_id=interview_id, role=participant)
                # Retain uncertainty if commit acknowledgement is lost. There is
                # no automatic retry, and withdrawal must still fence this entry.
                entry.session_may_exist = True
                await self.persistence.create_session(owner, interview_id, capture_id,
                    entry.receipts['recruiter'], entry.receipts['candidate'])
                entry.status = 'authorized_session_no_transcript'
            return self._view(entry)
