"""Synthetic-only tests. Real PG uses a new disposable container, never demo ports."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
from types import SimpleNamespace as N
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import select, func, text, delete
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request
from app.core.auth import token_hash
from app.db.models.recruiter import Recruiter, RecruiterSession, JobProfile, InterviewSchedule, InterviewInvitation
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn
from app.schemas.interview_transcript import FinalTranscriptEvent
from app.services.interview_transcripts import StorageConsentAuthority, TranscriptPersistenceService, TranscriptError


def event(capture, **patch):
    return FinalTranscriptEvent(**dict(dict(id=uuid4(), session_id=capture, sequence=1,
        role='recruiter', final=True, text='Clearly synthetic speech.', start_ms=0, end_ms=4000), **patch))


@pytest.mark.parametrize('patch', [dict(role='visitor'), dict(final=False), dict(final=1),
    dict(sequence=0), dict(sequence=True), dict(start_ms=-1), dict(start_ms=5,end_ms=4),
    dict(end_ms=1.5), dict(text=''), dict(text='  '), dict(text='x'*1001), dict(text='unsafe\x00')])
def test_final_event_validation_is_sanitized(patch):
    with pytest.raises(ValidationError) as failure:
        event(uuid4(), **patch)
    assert 'Clearly synthetic speech.' not in str(failure.value)


@pytest.fixture(scope='module')
def pg():
    if os.environ.get('TRANSCRIPT_PG_TEST') != '1':
        pytest.skip('Enable explicit disposable PostgreSQL transcript tests')
    container='talenttrace-transcript-test-'+uuid4().hex[:10]
    image=json.loads(subprocess.run(['docker','inspect','talenttrace-f4-local-20261012'],capture_output=True,text=True,check=True).stdout)[0]['Config']['Image']
    password=secrets.token_urlsafe(32)
    with socket.socket() as probe:
        probe.bind(('127.0.0.1',54402))
    result=subprocess.run(['docker','run','--pull=never','--rm','-d','--name',container,
        '-p','127.0.0.1:54402:5432','-e','POSTGRES_USER=transcript_test','-e','POSTGRES_DB=transcript_test',
        '-e','POSTGRES_PASSWORD='+password,image],capture_output=True,text=True)
    assert result.returncode==0,'Disposable PostgreSQL could not start'
    def sql(value):
        done=subprocess.run(['docker','exec','-i',container,'psql','-v','ON_ERROR_STOP=1',
            '-U','transcript_test','-d','transcript_test'],input=value,text=True,capture_output=True)
        assert done.returncode==0,'Disposable migration/verification failed'
        return done.stdout
    def migration(target, down=False):
        output=StringIO();cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'),output_buffer=output)
        (command.downgrade if down else command.upgrade)(cfg,target,sql=True)
        sql(output.getvalue())
    try:
        for _ in range(60):
            ready=subprocess.run(['docker','exec',container,'pg_isready','-U','transcript_test'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(.25)
        else:pytest.fail('Disposable PostgreSQL not ready')
        migration('0009_bulk_scheduling')
        marker=uuid4()
        sql(f"INSERT INTO recruiters(id,email,password_hash,active) VALUES ('{marker}','migration-sentinel@example.test','unused',true);")
        migration('0009_bulk_scheduling:0010_interview_transcripts')
        migration('0010_interview_transcripts:0009_bulk_scheduling',down=True)
        migration('0009_bulk_scheduling:0010_interview_transcripts')
        assert '1' in sql(f"SELECT count(*) FROM recruiters WHERE id='{marker}';")
        yield URL.create('postgresql+asyncpg',username='transcript_test',password=password,
            host='127.0.0.1',port=54402,database='transcript_test')
    finally:
        subprocess.run(['docker','stop',container],capture_output=True,check=True)


async def fixture(url):
    assert url.host=='127.0.0.1' and url.port==54402 and url.database=='transcript_test'
    engine=create_async_engine(url,echo=False,hide_parameters=True)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    now=[datetime.now(timezone.utc)];owner,job,interview,capture=uuid4(),uuid4(),uuid4(),uuid4()
    recruiter_token,candidate_token=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    async with factory.begin() as db:
        db.add(Recruiter(id=owner,email=f'{owner}@example.test',password_hash='unused',active=True));await db.flush()
        db.add(RecruiterSession(token_hash=token_hash(recruiter_token),recruiter_id=owner,expires_at=now[0]+timedelta(hours=1)))
        db.add(JobProfile(id=job,recruiter_id=owner,job_reference='TT-JOB-'+uuid4().hex[:16].upper(),job_title='Synthetic transcript fixture',revision=2,confirmed_snapshot={'synthetic':True},suggestions={},sources=[],scoring_weights={'skill':100,'experience':0,'education':0}));await db.flush()
        db.add(InterviewSchedule(id=interview,recruiter_id=owner,job_id=job,batch_id=uuid4(),upload_id=uuid4(),criteria_revision=2,scoring_version='f2-coverage-v1',scheduled_at=now[0]-timedelta(minutes=1),timezone='Asia/Dhaka',duration_minutes=60,unscored_confirmed=False,screening_snapshot={}));await db.flush()
        db.add(InterviewInvitation(id=uuid4(),interview_id=interview,token_hash=token_hash(secrets.token_urlsafe(32)),candidate_session_hash=token_hash(candidate_token),expires_at=now[0]+timedelta(hours=1),revoked=False))
    authority=StorageConsentAuthority(factory,version='synthetic-storage-v1',clock=lambda:now[0])
    service=TranscriptPersistenceService(factory,authority,clock=lambda:now[0])
    def request(candidate=False, explicit=True):
        cookie=('talenttrace_interview='+candidate_token) if candidate else ('talenttrace_session='+recruiter_token)
        headers=[(b'x-talenttrace-request',b'1'),(b'cookie',cookie.encode())]
        if explicit:headers.append((b'x-talenttrace-storage-consent',b'synthetic-storage-v1'))
        return Request({'type':'http','method':'POST','path':'/synthetic-storage-consent','headers':headers})
    recruiter=await authority.accept(request(),capture_id=capture,interview_id=interview,job_id=job)
    candidate=await authority.accept(request(True),capture_id=capture,interview_id=interview)
    return N(engine=engine,factory=factory,now=now,owner=owner,job=job,interview=interview,capture=capture,
        authority=authority,service=service,recruiter=recruiter,candidate=candidate,request=request)


def run(pg, scenario):
    async def wrapped():
        f=await fixture(pg)
        try:await scenario(f)
        finally:await f.engine.dispose()
    asyncio.run(wrapped())


async def start(f):
    return await f.service.create_session(f.owner,f.interview,f.capture,f.recruiter,f.candidate)


def test_pg_valid_session_turns_repeated_speech_and_order(pg,caplog):
    async def scenario(f):
        row=await start(f);assert row.status=='active' and row.persistence_outcome=='pending'
        assert (await start(f)).id==row.id
        f.now[0]+=timedelta(seconds=10)
        late=event(f.capture,sequence=2,role='candidate',start_ms=4000,end_ms=8000)
        early=event(f.capture)
        await f.service.append_final(f.owner,late);await f.service.append_final(f.owner,early)
        rows=await f.service.list_turns(f.owner,f.interview)
        assert [r.id for r in rows]==[early.id,late.id] and rows[0].text==rows[1].text
        assert (await f.service.finish_session(f.owner,f.capture,completed=True)).persistence_outcome=='saved'
        assert 'Clearly synthetic speech.' not in caplog.text
    run(pg,scenario)


@pytest.mark.parametrize('missing',['recruiter','candidate','fabricated','altered','wrong_capture','wrong_issuer','expired'])
def test_pg_missing_or_untrusted_consent(pg,missing):
    async def scenario(f):
        recruiter,candidate=f.recruiter,f.candidate
        if missing=='recruiter':recruiter=None
        if missing=='candidate':candidate=None
        if missing=='fabricated':candidate={'verified':True,'role':'candidate'}
        if missing=='altered':candidate=replace(candidate,actor_id=uuid4())
        if missing=='wrong_capture':candidate=replace(candidate,capture_id=uuid4())
        if missing=='wrong_issuer':f.service.authority=StorageConsentAuthority(f.factory,version='synthetic-storage-v1')
        if missing=='expired':f.now[0]+=timedelta(minutes=6)
        with pytest.raises(TranscriptError,match='storage_consent_not_verified'):
            await f.service.create_session(f.owner,f.interview,f.capture,recruiter,candidate)
        async with f.factory() as db:assert await db.get(Capture,f.capture) is None
    run(pg,scenario)


def test_pg_authentication_and_explicit_storage_action_required(pg):
    async def scenario(f):
        for request,kwargs in [(f.request(explicit=False),dict(job_id=f.job)),
                (f.request(True),dict(job_id=f.job)),(f.request(),{} )]:
            with pytest.raises(TranscriptError):
                await f.authority.accept(request,capture_id=f.capture,interview_id=f.interview,**kwargs)
    run(pg,scenario)


def test_pg_duplicate_conflict_and_rollback(pg):
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10);value=event(f.capture)
        assert (await f.service.append_final(f.owner,value)).id==value.id
        assert (await f.service.append_final(f.owner,value)).id==value.id
        for changed in [value.model_copy(update={'text':'Different synthetic text'}),value.model_copy(update={'id':uuid4()})]:
            with pytest.raises(TranscriptError,match='transcript_identity_conflict'):
                await f.service.append_final(f.owner,changed)
        assert len(await f.service.list_turns(f.owner,f.interview))==1
        # Force an actual SQL failure after insertion; both insertion and state change roll back.
        from sqlalchemy import event as sa_event
        def fail(mapper,connection,target):connection.execute(text('SELECT 1/0'))
        sa_event.listen(Turn,'after_insert',fail)
        try:
            with pytest.raises(TranscriptError,match='transcript_storage_unavailable') as error:
                await f.service.append_final(f.owner,event(f.capture,sequence=2))
            assert not error.value.outcome_uncertain
        finally:sa_event.remove(Turn,'after_insert',fail)
        assert len(await f.service.list_turns(f.owner,f.interview))==1
    run(pg,scenario)


def test_pg_concurrent_speakers_and_duplicate_event(pg):
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10)
        a,b=event(f.capture),event(f.capture,sequence=2,role='candidate')
        await asyncio.gather(f.service.append_final(f.owner,a),f.service.append_final(f.owner,b),f.service.append_final(f.owner,a))
        assert len(await f.service.list_turns(f.owner,f.interview))==2
        with pytest.raises(TranscriptError):await f.service.list_turns(uuid4(),f.interview)
        with pytest.raises(TranscriptError):await f.service.append_final(uuid4(),event(f.capture,sequence=3))
    run(pg,scenario)


def test_pg_missing_interview_and_capture_and_future_time(pg):
    async def scenario(f):
        with pytest.raises(TranscriptError):await f.service.append_final(f.owner,event(uuid4()))
        await start(f)
        with pytest.raises(TranscriptError,match='invalid_recognition_time'):
            await f.service.append_final(f.owner,event(f.capture))
        with pytest.raises(TranscriptError):await f.service.list_turns(f.owner,uuid4())
        async with f.factory.begin() as db:await db.execute(delete(Capture).where(Capture.id==f.capture));await db.execute(delete(InterviewSchedule).where(InterviewSchedule.id==f.interview))
        with pytest.raises(TranscriptError,match='owned_interview_not_found'):await start(f)
    run(pg,scenario)


def test_pg_interruption_failed_partial_and_new_capture_identity(pg):
    async def scenario(f):
        await start(f)
        assert (await f.service.finish_session(f.owner,f.capture,completed=False,persistence_failed=True)).persistence_outcome=='failed'
        old=f.capture;f.capture=uuid4()
        with pytest.raises(TranscriptError):await start(f) # old receipts cannot authorize reconnect
        f.recruiter=await f.authority.accept(f.request(),capture_id=f.capture,interview_id=f.interview,job_id=f.job)
        f.candidate=await f.authority.accept(f.request(True),capture_id=f.capture,interview_id=f.interview)
        await start(f);f.now[0]+=timedelta(seconds=10)
        await f.service.append_final(f.owner,event(f.capture))
        row=await f.service.finish_session(f.owner,f.capture,completed=False)
        assert row.persistence_outcome=='partial' and row.id!=old
        with pytest.raises(TranscriptError,match='capture_closed'):
            await f.service.append_final(f.owner,event(f.capture,sequence=2))
    run(pg,scenario)


def test_pg_constraints_and_restrict_deletion(pg):
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10);await f.service.append_final(f.owner,event(f.capture))
        for model,key in [(InterviewSchedule,f.interview),(Capture,f.capture)]:
            with pytest.raises(IntegrityError):
                async with f.factory.begin() as db:await db.execute(delete(model).where(model.id==key))
        for patch in [dict(role='invalid'),dict(start_ms=-1),dict(end_ms=-1),dict(text=''),dict(text='x'*1001),dict(sequence=0)]:
            values=dict(id=uuid4(),session_id=f.capture,sequence=2,role='candidate',text='Synthetic',start_ms=0,end_ms=1,created_at=f.now[0]);values.update(patch)
            with pytest.raises(IntegrityError):
                async with f.factory.begin() as db:db.add(Turn(**values))
        assert len(await f.service.list_turns(f.owner,f.interview))==1
    run(pg,scenario)


def test_pg_commit_acknowledgement_loss_is_uncertain_and_reconcilable(pg):
    async def scenario(f):
        from sqlalchemy import event as sa_event
        from sqlalchemy.orm import Session
        from sqlalchemy.exc import OperationalError
        await start(f);f.now[0]+=timedelta(seconds=10);value=event(f.capture)
        def lost_ack(db):raise OperationalError('synthetic commit acknowledgement',{},Exception('unavailable'))
        sa_event.listen(Session,'after_commit',lost_ack)
        try:
            with pytest.raises(TranscriptError) as error:
                await f.service.append_final(f.owner,value)
            assert error.value.outcome_uncertain
        finally:sa_event.remove(Session,'after_commit',lost_ack)
        assert [r.id for r in await f.service.list_turns(f.owner,f.interview)]==[value.id]
        assert (await f.service.append_final(f.owner,value)).id==value.id
        assert len(await f.service.list_turns(f.owner,f.interview))==1
    run(pg,scenario)


def test_pg_lock_timeout_rolls_back_and_does_not_retry(pg):
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10)
        async with f.factory.begin() as blocker:
            await blocker.scalar(select(Capture).where(Capture.id==f.capture).with_for_update())
            before=time.monotonic()
            with pytest.raises(TranscriptError) as error:
                await f.service.append_final(f.owner,event(f.capture))
            assert not error.value.outcome_uncertain and time.monotonic()-before<5
        assert not await f.service.list_turns(f.owner,f.interview)
    run(pg,scenario)


def test_pg_revoked_candidate_and_stale_interview_cannot_start_capture(pg):
    async def scenario(f):
        async with f.factory.begin() as db:
            invite=await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==f.interview))
            invite.revoked=True
        with pytest.raises(TranscriptError,match='storage_consent_not_verified'):await start(f)
        async with f.factory.begin() as db:
            job=await db.get(JobProfile,f.job);job.revision+=1
        with pytest.raises(TranscriptError,match='interview_revision_changed'):await start(f)
    run(pg,scenario)


def test_pg_database_requires_both_consents_and_consistent_lifecycle(pg):
    async def scenario(f):
        base=dict(id=f.capture,interview_id=f.interview,started_at=f.now[0],ended_at=None,
            recruiter_consented_at=f.now[0],candidate_consented_at=f.now[0],consent_version='synthetic-v1',
            status='active',persistence_outcome='pending')
        for patch in [dict(recruiter_consented_at=None),dict(candidate_consented_at=None),
                dict(candidate_consented_at=f.now[0]+timedelta(seconds=1)),dict(status='completed'),
                dict(ended_at=f.now[0]-timedelta(seconds=1)),dict(persistence_outcome='invented')]:
            with pytest.raises(IntegrityError):
                async with f.factory.begin() as db:db.add(Capture(**dict(base,**patch)))
        assert await start(f)
    run(pg,scenario)


def test_pg_consent_coordinator_creates_metadata_only_and_withdraws(pg):
    from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION
    async def scenario(f):
        authority=StorageConsentAuthority(f.factory,version=CONSENT_VERSION,clock=lambda:f.now[0])
        service=TranscriptPersistenceService(f.factory,authority,clock=lambda:f.now[0])
        coordinator=TranscriptConsentCoordinator(authority,service)
        def request(candidate=False):
            original=f.request(candidate)
            headers=[(k,v) for k,v in original.scope['headers'] if k!=b'x-talenttrace-storage-consent']
            return Request({**original.scope,'headers':headers+[(b'x-talenttrace-storage-consent',CONSENT_VERSION.encode())]})
        capture=(await coordinator.prepare(request(),interview_id=f.interview,job_id=f.job))['capture_id']
        await coordinator.decide(request(),interview_id=f.interview,job_id=f.job,capture_id=capture,decision='accept')
        async with f.factory() as db:assert await db.get(Capture,capture) is None
        result=await coordinator.decide(request(True),interview_id=f.interview,capture_id=capture,decision='accept')
        assert result['status']=='authorized_session_no_transcript' and not result['transcript_saved']
        await coordinator.decide(request(True),interview_id=f.interview,capture_id=capture,decision='accept')
        async with f.factory() as db:
            row=await db.get(Capture,capture)
            assert row.consent_version==CONSENT_VERSION and row.persistence_outcome=='pending'
            assert await db.scalar(select(func.count()).select_from(Capture).where(Capture.id==capture))==1
            assert await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id==capture))==0
        await coordinator.decide(request(True),interview_id=f.interview,capture_id=capture,decision='withdraw')
        async with f.factory() as db:
            row=await db.get(Capture,capture)
            assert row.status=='interrupted' and row.persistence_outcome=='failed'
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await coordinator.decide(request(),interview_id=f.interview,job_id=f.job,capture_id=capture,decision='accept')
    run(pg,scenario)


def test_pg_consent_participants_cannot_impersonate_or_bypass_window(pg):
    async def scenario(f):
        # Same authority helper used by coordinator prepare/accept/withdraw.
        for request,interview,job in [(f.request(True),f.interview,f.job),
                (f.request(),f.interview,None),(f.request(True),uuid4(),None),
                (f.request(),f.interview,uuid4())]:
            with pytest.raises(TranscriptError):
                await f.authority.participant(request,interview_id=interview,job_id=job)
        assert (await f.authority.participant(f.request(),interview_id=f.interview,job_id=f.job))[0]=='recruiter'
        assert (await f.authority.participant(f.request(True),interview_id=f.interview))[0]=='candidate'
        async with f.factory.begin() as db:
            row=await db.get(InterviewSchedule,f.interview)
            row.scheduled_at=datetime.now(timezone.utc)+timedelta(hours=2)
        with pytest.raises(TranscriptError):
            await f.authority.participant(f.request(True),interview_id=f.interview)
    run(pg,scenario)
