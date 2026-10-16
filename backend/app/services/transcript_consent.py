"""Inactive storage-consent integration. No routes, text writer or caption hook.

The lock/revocation fence is process-local, NOT durable. Do not activate transcript
writing until transactional revocation, read suppression and deletion are built.
"""
import asyncio
from dataclasses import dataclass, field
from uuid import UUID, uuid4

from app.services.interview_transcripts import TranscriptError


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


class TranscriptConsentCoordinator:
    """Internal single-process orchestration, deliberately absent from app startup.

    Receipts stay private in RAM. An authenticated adapter may call prepare and
    decide, but must not enable real storage on the strength of this prototype.
    One capture per interview per coordinator lifetime; no reset after revocation.
    """
    def __init__(self, authority, persistence):
        if authority.version != CONSENT_VERSION or persistence.authority is not authority:
            raise TranscriptError('invalid_consent_version')
        self.authority, self.persistence = authority, persistence
        self._entries = {}
        self._lock = asyncio.Lock()

    def _view(self, entry):
        return {'capture_id': entry.capture_id, 'consent_version': CONSENT_VERSION,
                'status': entry.status, 'transcript_saved': False,
                'transcript_writing_enabled': False,
                'durable_revocation_enforced': False,
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
            if entry.owner != owner:
                raise TranscriptError('storage_consent_not_verified')
            return {**self._view(entry), 'wording': CONSENT_WORDING}

    async def decide(self, request, *, interview_id, capture_id, decision, job_id=None):
        if decision not in ('accept', 'decline', 'withdraw'):
            raise TranscriptError('invalid_storage_decision')
        # All awaits through metadata creation are inside the same process lock.
        # This serializes withdrawal with consent/session creation, not turn writes.
        async with self._lock:
            role, actor, owner = await self.authority.participant(request, interview_id=interview_id, job_id=job_id)
            entry = self._entries.get(interview_id)
            if entry is None or entry.capture_id != capture_id or entry.owner != owner:
                raise TranscriptError('storage_consent_not_verified')
            if decision in ('decline', 'withdraw'):
                self.authority.revoke(interview_id)
                entry.receipts.clear()
                # Set the in-memory fence before any database cleanup attempt.
                entry.closure_pending = entry.session_may_exist
                entry.status = 'withdrawn' if decision == 'withdraw' else 'declined'
                if entry.closure_pending:
                    # No turns are written by this integration. Never call this
                    # deletion, or mark a transcript completed/saved.
                    await self.persistence.finish_session(owner, capture_id, completed=False)
                    entry.session_may_exist = False
                    entry.closure_pending = False
                return self._view(entry)
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
