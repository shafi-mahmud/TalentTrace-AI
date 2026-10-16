"""Offline F5 input boundary. No evaluation, provider calls, caching or writes."""
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from app.core.auth import current_recruiter
from app.db.models.recruiter import JobProfile
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn
from app.schemas.batch_screening import ReviewedJobSnapshot
from app.schemas.interview_transcript import CaptureEvidence, FinalTranscriptEvent
from app.schemas.screening import ScreeningCriterion
from app.services.interview_transcripts import TranscriptError, transaction
from app.services.transcript_consent import CONSENT_VERSION


class EvaluationInputError(Exception):
    """Fixed diagnostic codes only; never include source text or SQL."""


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True, hide_input_in_errors=True)


class CaptureReference(Contract):
    id: UUID
    started_at: datetime
    ended_at: datetime


class EvaluationInput(Contract):
    job_id: UUID
    interview_id: UUID
    batch_id: UUID
    upload_id: UUID
    criteria_revision: int = Field(ge=1)
    retention_deadline: datetime
    criteria: tuple[ScreeningCriterion, ...] = Field(min_length=1, max_length=50, repr=False)
    captures: tuple[CaptureReference, ...] = Field(min_length=1, max_length=100)
    turns: tuple[FinalTranscriptEvent, ...] = Field(min_length=1, max_length=1500, repr=False)
    scope: Literal['accepted_audio_only'] = 'accepted_audio_only'
    asr_review: Literal['unverified'] = 'unverified'
    warning: str = 'Finalized accepted audio only; ASR may be wrong. Missing evidence is not lack of skill.'


class EvidenceQuote(Contract):
    turn_id: UUID
    quote: str = Field(min_length=1, max_length=1000, repr=False)


def validate_quotes(source: EvaluationInput, quotes: tuple[EvidenceQuote, ...]):
    """Exact source verification, not factual correctness or semantic evaluation."""
    if not quotes or len(quotes) > 100:
        raise EvaluationInputError('evaluation_evidence_missing_or_unbounded')
    by_id = {turn.id: turn for turn in source.turns}
    for item in quotes:
        if (type(item) is not EvidenceQuote or not item.quote.strip()
                or item.turn_id not in by_id or item.quote not in by_id[item.turn_id].text):
            raise EvaluationInputError('evaluation_evidence_not_in_source')
    return quotes


def build_input(parent, snapshot, captures, rows):
    """Called only under the authenticated interview privacy lock; not an API."""
    if not captures or len(captures) > 100 or not rows or len(rows) > 1500:
        raise EvaluationInputError('evaluation_transcript_missing_or_unbounded')
    try:
        job = ReviewedJobSnapshot.model_validate(snapshot)
        # Arrival/query order must not change pairing or the input fingerprint.
        # Preserve per-capture sequence; never rewrite source text or event IDs.
        captures=sorted(captures,key=lambda c:(c.started_at,c.id))
        capture_order={capture.id:index for index,capture in enumerate(captures)}
        rows=sorted(rows,key=lambda row:(capture_order.get(row.session_id,-1),row.sequence,row.id))
        identities, sequences, capture_ids, refs = set(), set(), set(), []
        durations = {}
        for capture in captures:
            if capture.id in capture_ids or capture.interview_id != parent.id:
                raise EvaluationInputError('evaluation_identity_conflict')
            capture_ids.add(capture.id)
            if (capture.status != 'completed' or capture.persistence_outcome != 'saved'
                    or capture.ended_at is None or capture.ended_at < capture.started_at
                    or not capture.recruiter_consented_at or not capture.candidate_consented_at
                    or capture.recruiter_consented_at > capture.started_at
                    or capture.candidate_consented_at > capture.started_at
                    or capture.consent_version != CONSENT_VERSION):
                raise EvaluationInputError('evaluation_transcript_not_finalized')
            evidence = CaptureEvidence.model_validate(capture.capture_summary)
            count = sum(row.session_id == capture.id for row in rows)
            if (evidence.audio_outcome != 'drained' or evidence.commit_uncertain
                    or evidence.expected_turns != count or evidence.acknowledged_turns != count
                    or evidence.accepted_samples != evidence.processed_samples):
                raise EvaluationInputError('evaluation_completeness_unverified')
            refs.append(CaptureReference(id=capture.id, started_at=capture.started_at, ended_at=capture.ended_at))
            durations[capture.id] = int((capture.ended_at-capture.started_at).total_seconds()*1000)
        turns = []
        for row in rows:
            key = (row.session_id, row.sequence)
            if row.id in identities or key in sequences or row.session_id not in capture_ids:
                raise EvaluationInputError('evaluation_identity_conflict')
            identities.add(row.id); sequences.add(key)
            if row.end_ms > durations[row.session_id]:
                raise EvaluationInputError('evaluation_recognition_time_invalid')
            turns.append(FinalTranscriptEvent(id=row.id, session_id=row.session_id,
                sequence=row.sequence, role=row.role, final=True, text=row.text,
                start_ms=row.start_ms, end_ms=row.end_ms))
        if {turn.role for turn in turns} != {'candidate', 'recruiter'}:
            raise EvaluationInputError('evaluation_speaker_evidence_missing')
        return EvaluationInput(job_id=parent.job_id, interview_id=parent.id,
            batch_id=parent.batch_id, upload_id=parent.upload_id, criteria_revision=parent.criteria_revision,
            retention_deadline=parent.transcript_retention_deadline, criteria=tuple(job.criteria),
            captures=tuple(refs), turns=tuple(turns))
    except ValidationError:
        raise EvaluationInputError('evaluation_source_invalid') from None


class PostInterviewInputService:
    def __init__(self, transcript_storage):
        self.storage = transcript_storage

    async def prepare(self, request, *, job_id: UUID, interview_id: UUID, revision: int):
        # No cached payload is an authorization capability. Recheck for every use.
        async with transaction(self.storage.factory) as db:
            return await self.load(db,request,job_id=job_id,interview_id=interview_id,revision=revision)

    async def load(self,db,request,*,job_id,interview_id,revision):
        owner = await current_recruiter(request, db)
        parent = await self.storage._owned(db, owner.id, interview_id)
        if parent.job_id != job_id:
            raise TranscriptError('owned_interview_not_found')
        if parent.transcript_retention_deadline is None:
            raise EvaluationInputError('evaluation_retention_unestablished')
        job = await db.get(JobProfile, job_id)
        if (type(revision) is not int or revision != parent.criteria_revision
                or job.revision != revision or job.confirmed_snapshot is None):
            raise EvaluationInputError('evaluation_revision_changed')
        captures = list((await db.scalars(select(Capture).where(Capture.interview_id == interview_id)
            .order_by(Capture.started_at, Capture.id).limit(101))).all())
        rows = list((await db.scalars(select(Turn).join(Capture).where(Capture.interview_id == interview_id)
            .order_by(Capture.started_at, Capture.id, Turn.sequence, Turn.id).limit(1501))).all())
        # Parent-row-first locking serializes this read with withdrawal and writers.
        return build_input(parent, job.confirmed_snapshot, captures, rows)
