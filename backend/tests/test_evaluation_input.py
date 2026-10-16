"""Synthetic F5 input tests; optional PG fixture creates/removes its own database."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import select, func

from app.db.models.recruiter import JobProfile, InterviewSchedule, CandidateScoreRecord
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn
from app.services.evaluation_input import (build_input, validate_quotes, EvidenceQuote,
    EvaluationInputError, PostInterviewInputService)
from app.services.interview_transcripts import TranscriptError
from app.services.transcript_consent import CONSENT_VERSION
from test_interview_transcripts import pg, run, start, event


def source():
    now = datetime.now(timezone.utc)
    parent = N(id=uuid4(), job_id=uuid4(), batch_id=uuid4(), upload_id=uuid4(), criteria_revision=2,
        transcript_retention_deadline=now+timedelta(days=30))
    snapshot = dict(job_reference='TT-JOB-1234567890ABCDEF', job_title='Synthetic engineer',
        criteria_confirmed=True, criteria=[dict(criterion_id='python', category='skill',
            description='Python', is_hard=False)])
    capture = N(id=uuid4(), interview_id=parent.id, started_at=now, ended_at=now+timedelta(seconds=10),
        recruiter_consented_at=now, candidate_consented_at=now, consent_version=CONSENT_VERSION,
        status='completed', persistence_outcome='saved', capture_summary=dict(audio_outcome='drained',
            expected_turns=2, acknowledged_turns=2, accepted_samples={'recruiter':64000,'candidate':64000},
            processed_samples={'recruiter':64000,'candidate':64000}, scope='accepted_audio_only', commit_uncertain=False))
    rows = [N(id=uuid4(), session_id=capture.id, sequence=i+1, role=role, text=text,
        start_ms=i*4000, end_ms=(i+1)*4000) for i,(role,text) in enumerate([
            ('recruiter','What is a Python list?'), ('candidate','A list is an ordered collection.')])]
    return parent, snapshot, [capture], rows


def test_valid_finalized_input_and_exact_evidence(caplog):
    data = build_input(*source())
    quote = EvidenceQuote(turn_id=data.turns[1].id, quote='ordered collection')
    assert validate_quotes(data,(quote,)) == (quote,)
    assert data.scope == 'accepted_audio_only' and data.asr_review == 'unverified'
    assert 'A list is' not in repr(data) and 'A list is' not in caplog.text
    assert data.turns[0].session_id == data.captures[0].id


def test_source_arrival_order_does_not_change_pairing_or_fingerprint():
    from app.services.interview_qa import pair_transcript
    from app.services.interview_analysis import fingerprint
    parent,snapshot,captures,rows=source()
    ordered=build_input(parent,snapshot,captures,rows)
    shuffled=build_input(parent,snapshot,list(reversed(captures)),list(reversed(rows)))
    assert fingerprint(ordered)==fingerprint(shuffled)
    assert pair_transcript(ordered)==pair_transcript(shuffled)
    assert rows[0].sequence==1


@pytest.mark.parametrize('change', ['active','interrupted','partial','failed','no_end',
    'missing_summary','uncertain_commit','different_count','different_samples','no_consent','wrong_version'])
def test_incomplete_and_contradictory_metadata_refused(change):
    parent,snapshot,captures,rows = source(); c=captures[0]
    if change in {'active','interrupted'}:c.status=change
    elif change in {'partial','failed'}:c.persistence_outcome=change
    elif change=='no_end':c.ended_at=None
    elif change=='missing_summary':c.capture_summary=None
    elif change=='uncertain_commit':c.capture_summary['commit_uncertain']=True
    elif change=='different_count':c.capture_summary['expected_turns']=1
    elif change=='different_samples':c.capture_summary['processed_samples']['candidate']=1
    elif change=='no_consent':c.candidate_consented_at=None
    elif change=='wrong_version':c.consent_version='unapproved'
    with pytest.raises(EvaluationInputError):build_input(parent,snapshot,captures,rows)


@pytest.mark.parametrize('change', ['no_speaker','candidate_only','duplicate_id','duplicate_sequence',
    'foreign_capture','empty_text','no_turns','outside_capture'])
def test_missing_and_duplicate_source_evidence_refused(change):
    parent,snapshot,captures,rows = source()
    if change=='no_speaker':rows[1].role=None
    elif change=='candidate_only':rows[0].role='candidate'
    elif change=='duplicate_id':rows[1].id=rows[0].id
    elif change=='duplicate_sequence':rows[1].sequence=rows[0].sequence
    elif change=='foreign_capture':rows[1].session_id=uuid4()
    elif change=='empty_text':rows[1].text=' '
    elif change=='no_turns':rows=[]
    elif change=='outside_capture':rows[1].end_ms=999999
    with pytest.raises(EvaluationInputError):build_input(parent,snapshot,captures,rows)


@pytest.mark.parametrize('quote', ['', 'invented technical evidence', 'ORDERED COLLECTION'])
def test_unsupported_or_missing_quotations_do_not_become_evidence(quote):
    data=build_input(*source())
    if not quote:references=()
    else:references=(EvidenceQuote(turn_id=data.turns[1].id,quote=quote),)
    with pytest.raises(EvaluationInputError):validate_quotes(data,references)
    with pytest.raises(EvaluationInputError):
        validate_quotes(data,(EvidenceQuote(turn_id=uuid4(),quote='ordered collection'),))


async def completed(f):
    await start(f);f.now[0]+=timedelta(seconds=10)
    await f.service.append_final(f.owner,event(f.capture,role='recruiter'))
    await f.service.append_final(f.owner,event(f.capture,role='candidate',sequence=2))
    await f.service.finish_session(f.owner,f.capture,completed=True,evidence=source()[2][0].capture_summary)
    async with f.factory.begin() as db:
        job=await db.get(JobProfile,f.job)
        snapshot=source()[1];snapshot['job_reference']=job.job_reference
        job.confirmed_snapshot=snapshot
        capture=await db.get(Capture,f.capture);capture.consent_version=CONSENT_VERSION


def test_pg_authenticated_current_finalized_input_without_writes(pg):
    async def scenario(f):
        await completed(f)
        service=PostInterviewInputService(f.service)
        data=await service.prepare(f.request(),job_id=f.job,interview_id=f.interview,revision=2)
        assert len(data.turns)==2 and data.upload_id
        with pytest.raises(HTTPException):
            await service.prepare(f.request(True),job_id=f.job,interview_id=f.interview,revision=2)
        with pytest.raises(TranscriptError):
            await service.prepare(f.request(),job_id=uuid4(),interview_id=f.interview,revision=2)
        with pytest.raises(EvaluationInputError,match='evaluation_revision_changed'):
            await service.prepare(f.request(),job_id=f.job,interview_id=f.interview,revision=3)
        async with f.factory() as db:
            assert await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id==f.capture))==2
            assert await db.scalar(select(func.count()).select_from(CandidateScoreRecord).where(CandidateScoreRecord.job_id==f.job))==0
    run(pg,scenario)


@pytest.mark.parametrize('block',['withdrawn','expired','unestablished','active','other_recruiter'])
def test_pg_privacy_and_authorization_fence(pg,block):
    async def scenario(f):
        await completed(f)
        service=PostInterviewInputService(f.service)
        async with f.factory.begin() as db:
            row=await db.get(InterviewSchedule,f.interview)
            if block=='withdrawn':row.transcript_storage_revoked_at=f.now[0]
            elif block=='expired':row.transcript_retention_deadline=f.now[0]
            elif block=='unestablished':row.transcript_retention_deadline=None
            elif block=='active':
                capture=await db.get(Capture,f.capture)
                capture.status='active';capture.ended_at=None
        if block=='other_recruiter':
            from test_interview_transcripts import fixture
            other=await fixture(pg)
            try:
                with pytest.raises(TranscriptError,match='owned_interview_not_found'):
                    await service.prepare(other.request(),job_id=f.job,interview_id=f.interview,revision=2)
            finally:await other.engine.dispose()
        else:
            with pytest.raises((TranscriptError,EvaluationInputError)):
                await service.prepare(f.request(),job_id=f.job,interview_id=f.interview,revision=2)
    run(pg,scenario)
