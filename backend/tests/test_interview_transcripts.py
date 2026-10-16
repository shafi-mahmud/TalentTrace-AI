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
            ready=subprocess.run(['docker','exec',container,'pg_isready','-h','127.0.0.1','-U','transcript_test','-d','transcript_test'],capture_output=True)
            if ready.returncode==0:break
            time.sleep(.25)
        else:pytest.fail('Disposable PostgreSQL not ready')
        migration('0009_bulk_scheduling')
        marker=uuid4()
        sql(f"INSERT INTO recruiters(id,email,password_hash,active) VALUES ('{marker}','migration-sentinel@example.test','unused',true);")
        migration('0009_bulk_scheduling:0010_interview_transcripts')
        migration('0010_interview_transcripts:0009_bulk_scheduling',down=True)
        migration('0009_bulk_scheduling:0010_interview_transcripts')
        migration('0010_interview_transcripts:0012_transcript_privacy_guard')
        migration('0012_transcript_privacy_guard:0011_application_views',down=True)
        migration('0011_application_views:0012_transcript_privacy_guard')
        assert '1' in sql("SELECT count(*) FROM information_schema.columns WHERE table_name='interview_schedules' AND column_name='transcript_storage_revoked_at' AND data_type='timestamp with time zone';")
        assert '1' in sql(f"SELECT count(*) FROM recruiters WHERE id='{marker}';")
        migration('0012_transcript_privacy_guard:0013_transcript_lifecycle')
        migration('0013_transcript_lifecycle:0012_transcript_privacy_guard',down=True)
        migration('0012_transcript_privacy_guard:0013_transcript_lifecycle')
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
        with pytest.raises(TranscriptError,match='capture_completeness_unverified'):
            await f.service.finish_session(f.owner,f.capture,completed=True)
        assert (await f.service.finish_session(f.owner,f.capture,completed=True,evidence={
            'audio_outcome':'drained','expected_turns':2,'acknowledged_turns':2,'scope':'accepted_audio_only','commit_uncertain':False,
            'accepted_samples':{'recruiter':1,'candidate':1},'processed_samples':{'recruiter':1,'candidate':1}})).persistence_outcome=='saved'
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


def test_pg_durable_revocation_fresh_services_duplicate_events_and_isolation(pg):
    async def scenario(f):
        other=await fixture(pg)
        # Distinct engine/pool and fresh authority: no shared consent/revocation RAM.
        engine=create_async_engine(pg,echo=False,hide_parameters=True)
        factory=async_sessionmaker(engine,expire_on_commit=False)
        authority=StorageConsentAuthority(factory,version=f.authority.version,clock=lambda:f.now[0])
        service=TranscriptPersistenceService(factory,authority,clock=lambda:f.now[0])
        try:
            await start(f);f.now[0]+=timedelta(seconds=10)
            value=event(f.capture);await f.service.append_final(f.owner,value)
            assert len(await service.list_turns(f.owner,f.interview))==1
            assert await authority.withdraw(f.request(True),interview_id=f.interview)==f.owner
            async with factory() as db:
                stamp=(await db.get(InterviewSchedule,f.interview)).transcript_storage_revoked_at
                assert stamp is not None
                # Physical text remains, but application access is fenced.
                assert await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id==f.capture))==1
            await authority.withdraw(f.request(),interview_id=f.interview,job_id=f.job)
            async with factory() as db:
                assert (await db.get(InterviewSchedule,f.interview)).transcript_storage_revoked_at==stamp
            for operation in [service.list_turns(f.owner,f.interview),
                    f.service.append_final(f.owner,value), # Existing event must not leak on replay.
                    service.append_final(f.owner,event(f.capture,sequence=2)),
                    f.service.create_session(f.owner,f.interview,f.capture,f.recruiter,f.candidate),
                    service.finish_session(f.owner,f.capture,completed=True),
                    f.authority.accept(f.request(),capture_id=uuid4(),interview_id=f.interview,job_id=f.job)]:
                with pytest.raises(TranscriptError,match='storage_authorization_revoked'):await operation
            await start(other)
            other.now[0]+=timedelta(seconds=10)
            await other.service.append_final(other.owner,event(other.capture))
            assert len(await other.service.list_turns(other.owner,other.interview))==1
        finally:
            await engine.dispose();await other.engine.dispose()
    run(pg,scenario)


def test_pg_revocation_survives_new_python_process(pg):
    async def scenario(f):
        import sys
        await start(f);f.now[0]+=timedelta(seconds=10)
        await f.service.append_final(f.owner,event(f.capture))
        await f.authority.withdraw(f.request(True),interview_id=f.interview)
        child_env=os.environ.copy()
        child_env.update(TEST_PRIVACY_URL=pg.render_as_string(hide_password=False),
            TEST_PRIVACY_OWNER=str(f.owner),TEST_PRIVACY_INTERVIEW=str(f.interview),TEST_PRIVACY_CAPTURE=str(f.capture))
        code='''
import asyncio, json, os
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.services.interview_transcripts import StorageConsentAuthority, TranscriptPersistenceService, TranscriptError
from app.schemas.interview_transcript import FinalTranscriptEvent
async def main():
    engine=create_async_engine(os.environ['TEST_PRIVACY_URL'],hide_parameters=True)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    authority=StorageConsentAuthority(factory,version='synthetic-storage-v1')
    service=TranscriptPersistenceService(factory,authority)
    owner=UUID(os.environ['TEST_PRIVACY_OWNER']);interview=UUID(os.environ['TEST_PRIVACY_INTERVIEW'])
    event=FinalTranscriptEvent(id=uuid4(),session_id=UUID(os.environ['TEST_PRIVACY_CAPTURE']),sequence=2,
        role='candidate',final=True,text='Synthetic restart test.',start_ms=0,end_ms=1)
    codes=[]
    try:
        for operation in (service.list_turns(owner,interview),service.append_final(owner,event)):
            try: await operation;codes.append('unexpected_access')
            except TranscriptError as error: codes.append(error.code)
        print(json.dumps(codes))
    finally: await engine.dispose()
asyncio.run(main())
'''
        completed=await asyncio.to_thread(subprocess.run,[sys.executable,'-c',code],
            env=child_env,text=True,capture_output=True,timeout=45)
        assert completed.returncode==0,'Isolated privacy subprocess failed'
        assert json.loads(completed.stdout)==['storage_authorization_revoked']*2
    run(pg,scenario)


@pytest.mark.parametrize('winner',['write','withdraw'])
def test_pg_withdrawal_and_inflight_write_serialization(pg,winner):
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10)
        authority=StorageConsentAuthority(f.factory,version=f.authority.version,clock=lambda:f.now[0])
        entered,release=asyncio.Event(),asyncio.Event()
        order=[]
        if winner=='write':
            original=f.service._owned
            async def paused(*args,**kwargs):
                result=await original(*args,**kwargs)
                if not kwargs.get('current'):
                    entered.set();await release.wait()
                return result
            f.service._owned=paused
        else:
            original=authority._participant
            async def paused(*args,**kwargs):
                result=await original(*args,**kwargs)
                entered.set();await release.wait();return result
            authority._participant=paused
        async def write():
            try:
                await f.service.append_final(f.owner,event(f.capture))
                order.append('write_committed')
            except TranscriptError as error:
                assert error.code=='storage_authorization_revoked';order.append('write_denied')
        async def withdraw():
            await authority.withdraw(f.request(True),interview_id=f.interview)
            order.append('withdraw_committed')
        first=asyncio.create_task(write() if winner=='write' else withdraw())
        await asyncio.wait_for(entered.wait(),2)
        second=asyncio.create_task(withdraw() if winner=='write' else write())
        await asyncio.sleep(.1);assert not second.done()
        release.set();await asyncio.gather(first,second)
        assert order==(['write_committed','withdraw_committed'] if winner=='write'
            else ['withdraw_committed','write_denied'])
        async with f.factory() as db:
            assert await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id==f.capture))==(1 if winner=='write' else 0)
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await f.service.append_final(f.owner,event(f.capture,sequence=2))
    run(pg,scenario)


def test_pg_revocation_without_capture_and_failed_cleanup(pg):
    from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION
    async def scenario(f):
        authority=StorageConsentAuthority(f.factory,version=CONSENT_VERSION,clock=lambda:f.now[0])
        service=TranscriptPersistenceService(f.factory,authority,clock=lambda:f.now[0])
        coordinator=TranscriptConsentCoordinator(authority,service)
        # Fresh coordinator has no local entry; authenticated withdrawal still commits.
        view=await coordinator.decide(f.request(True),interview_id=f.interview,
            capture_id=uuid4(),decision='withdraw')
        assert view['withdrawal_committed'] and view['session_closure_pending']
        assert not view['deletion_verified']
        # A failed session cleanup cannot remove that independent transaction.
        with pytest.raises(TranscriptError):await service.finish_session(f.owner,uuid4(),completed=False)
        async with f.factory() as db:
            assert (await db.get(InterviewSchedule,f.interview)).transcript_storage_revoked_at is not None
        fresh=StorageConsentAuthority(f.factory,version=CONSENT_VERSION)
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await fresh.participant(f.request(True),interview_id=f.interview)
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await coordinator.prepare(f.request(True),interview_id=f.interview)
    run(pg,scenario)


def test_pg_coordinator_cleanup_failure_cannot_undo_committed_withdrawal(pg):
    from unittest.mock import AsyncMock
    from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION, _Pending
    async def scenario(f):
        await start(f)
        f.authority.version=CONSENT_VERSION
        coordinator=TranscriptConsentCoordinator(f.authority,f.service)
        coordinator._entries[f.interview]=_Pending(f.capture,f.owner,
            status='authorized_session_no_transcript',session_may_exist=True)
        original=f.service.finish_session
        f.service.finish_session=AsyncMock(side_effect=TranscriptError('transcript_storage_unavailable'))
        with pytest.raises(TranscriptError):
            await coordinator.decide(f.request(True),interview_id=f.interview,
                capture_id=f.capture,decision='withdraw')
        assert coordinator._entries[f.interview].withdrawal_committed
        async with f.factory() as db:
            assert (await db.get(InterviewSchedule,f.interview)).transcript_storage_revoked_at is not None
            assert (await db.get(Capture,f.capture)).status=='active'  # Cleanup really did not happen.
        independent=TranscriptPersistenceService(f.factory,StorageConsentAuthority(f.factory,version=CONSENT_VERSION))
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await independent.list_turns(f.owner,f.interview)
        f.service.finish_session=original
        assert not (await coordinator.decide(f.request(True),interview_id=f.interview,
            capture_id=f.capture,decision='withdraw'))['session_closure_pending']
    run(pg,scenario)


def test_privacy_migration_has_one_linear_head():
    from alembic.script import ScriptDirectory
    cfg=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    scripts=ScriptDirectory.from_config(cfg)
    assert scripts.get_heads()==['0013_transcript_lifecycle']
    assert scripts.get_revision('0012_transcript_privacy_guard').down_revision=='0011_application_views'
    assert scripts.get_revision('0011_application_views').down_revision=='0010_interview_transcripts'


def test_pg_withdrawal_commit_acknowledgement_loss_keeps_durable_fence(pg):
    async def scenario(f):
        from sqlalchemy import event as sa_event
        from sqlalchemy.orm import Session
        from sqlalchemy.exc import OperationalError
        await start(f)
        def lost_ack(db):raise OperationalError('synthetic withdrawal acknowledgement',{},Exception('unavailable'))
        sa_event.listen(Session,'after_commit',lost_ack)
        try:
            with pytest.raises(TranscriptError) as error:
                await f.authority.withdraw(f.request(True),interview_id=f.interview)
            assert error.value.outcome_uncertain
        finally:sa_event.remove(Session,'after_commit',lost_ack)
        # Failure to receive success cannot undo the transaction PostgreSQL committed.
        fresh=TranscriptPersistenceService(f.factory,StorageConsentAuthority(f.factory,version=f.authority.version))
        with pytest.raises(TranscriptError,match='storage_authorization_revoked'):
            await fresh.list_turns(f.owner,f.interview)
        assert await f.authority.withdraw(f.request(True),interview_id=f.interview)==f.owner
    run(pg,scenario)


def test_pg_unauthorized_withdrawal_cannot_set_marker(pg):
    async def scenario(f):
        for request,interview,job in [(f.request(True),f.interview,f.job),
                (f.request(),f.interview,None),(f.request(True),uuid4(),None),
                (f.request(),f.interview,uuid4())]:
            with pytest.raises(TranscriptError,match='storage_consent_not_verified'):
                await f.authority.withdraw(request,interview_id=interview,job_id=job)
        original=f.request()
        no_mutation=Request({**original.scope,'headers':[(k,v) for k,v in original.scope['headers']
            if k!=b'x-talenttrace-request']})
        with pytest.raises(TranscriptError,match='storage_consent_not_verified'):
            await f.authority.withdraw(no_mutation,interview_id=f.interview,job_id=f.job)
        async with f.factory() as db:
            assert (await db.get(InterviewSchedule,f.interview)).transcript_storage_revoked_at is None
    run(pg,scenario)


def test_pg_retention_expiry_denies_access_and_sweep_verifies_deletion(pg):
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10)
        await f.service.append_final(f.owner,event(f.capture))
        async with f.factory() as db:
            deadline=(await db.get(InterviewSchedule,f.interview)).transcript_retention_deadline
            assert deadline <= f.now[0]+timedelta(days=30)
        f.now[0]=deadline
        with pytest.raises(TranscriptError,match='transcript_retention_expired'):
            await f.service.list_turns(f.owner,f.interview)
        with pytest.raises(TranscriptError,match='transcript_retention_expired'):
            await f.service.append_final(f.owner,event(f.capture,sequence=2))
        privacy=TranscriptPrivacyService(f.service)
        assert (await privacy.sweep())['failed']==0
        async with f.factory() as db:
            row=await db.get(InterviewSchedule,f.interview)
            assert row.transcript_deletion_status=='deleted' and row.transcript_storage_revoked_at
            assert await db.get(Capture,f.capture) is None
            assert await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id==f.capture))==0
        await privacy.delete_revoked(f.owner,f.interview) # Idempotent.
    run(pg,scenario)


def test_pg_after_window_candidate_privacy_cookie_and_unauthorized_deletion(pg):
    from app.services.transcript_privacy import TranscriptPrivacyService, PRIVACY_COOKIE
    async def scenario(f):
        privacy=TranscriptPrivacyService(f.service)
        await start(f)
        raw,expires=await privacy.issue_candidate_access(f.request(True),f.interview)
        request=Request({'type':'http','method':'POST','headers':[
            (b'x-talenttrace-request',b'1'),(b'cookie',(PRIVACY_COOKIE+'='+raw).encode())]})
        async with f.factory.begin() as db:
            row=await db.get(InterviewSchedule,f.interview)
            row.scheduled_at=datetime.now(timezone.utc)-timedelta(days=1)
            invite=await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==f.interview))
            invite.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
        with pytest.raises(TranscriptError):await f.authority.participant(f.request(True),interview_id=f.interview)
        from fastapi import HTTPException
        with pytest.raises((TranscriptError,HTTPException)):
            await privacy.withdraw(request,uuid4())
        result=await privacy.withdraw(request,f.interview)
        assert result['withdrawn'] and result['deletion_verified']
        assert (await privacy.withdraw(request,f.interview))['deletion_verified']
    run(pg,scenario)


def test_pg_privacy_cleanup_failure_retry_and_concurrency(pg):
    from sqlalchemy import event as sa_event
    from sqlalchemy.exc import OperationalError
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        privacy=TranscriptPrivacyService(f.service)
        await start(f);f.now[0]+=timedelta(seconds=10)
        await f.service.append_final(f.owner,event(f.capture))
        def fail(connection,cursor,statement,parameters,context,many):
            if statement.lstrip().startswith('DELETE FROM interview_transcript_turns'):
                raise OperationalError('synthetic deletion failure',{},Exception('unavailable'))
        sa_event.listen(f.engine.sync_engine,'before_cursor_execute',fail)
        try:
            view=await privacy.withdraw(f.request(),f.interview,f.job)
            assert view['withdrawn'] and view['deletion_status']=='failed' and not view['deletion_verified']
            with pytest.raises(TranscriptError):await f.service.list_turns(f.owner,f.interview)
        finally:sa_event.remove(f.engine.sync_engine,'before_cursor_execute',fail)
        await asyncio.gather(privacy.delete_revoked(f.owner,f.interview),privacy.delete_revoked(f.owner,f.interview))
        assert (await privacy.status(f.request(),f.interview,f.job))['deletion_verified']
    run(pg,scenario)


def test_pg_trusted_caption_pipeline_saves_full_and_residual_turns(pg):
    from app.services.caption_transcript import CaptionTranscript
    from app.services.interview_captions import CaptionSession
    async def scenario(f):
        await start(f)
        runtime=N(storage=f.service,coordinator=N(_entries={f.interview:N(status='authorized_session_no_transcript',owner=f.owner,capture_id=f.capture)}))
        adapter=CaptionTranscript(runtime,f.interview)
        class Worker:
            async def start(self):pass
            async def close(self):pass
            async def transcribe(self,pcm):
                f.now[0]+=timedelta(seconds=1)
                return 'Synthetic trusted final speech.'
        messages=[]
        async def send(value):messages.append(value)
        session=CaptionSession(Worker,storage=adapter)
        for role in ('recruiter','candidate'):await session.connect(role,send)
        await session.approve('recruiter');await session.approve('candidate')
        for _ in range(40):await session.audio('recruiter',bytes(3200))
        await session.request_finish('recruiter')
        await session.audio('candidate',bytes(74))
        for role in ('recruiter','candidate'):
            await session.end_audio(role,dict(kind='end',frames=session.frames[role],
                samples=session.accepted_samples[role],captured_samples=session.accepted_samples[role]))
        await session.finalizer
        turns=await f.service.list_turns(f.owner,f.interview)
        assert len(turns)==2 and {turn.role for turn in turns}=={'recruiter','candidate'}
        assert [m for m in messages if m['kind']=='storage'][-1]['status']=='saved'
        async with f.factory() as db:
            capture=await db.get(Capture,f.capture)
            assert capture.status=='completed' and capture.capture_summary['acknowledged_turns']==2
            assert capture.capture_summary['accepted_samples']==capture.capture_summary['processed_samples']
        from app.services.transcript_privacy import TranscriptPrivacyService
        assert (await TranscriptPrivacyService(f.service).withdraw(f.request(True),f.interview))['deletion_verified']
    run(pg,scenario)


def test_pg_finalization_after_window_is_bounded_and_not_general_join_access(pg):
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(seconds=10)
        deadline=await f.service.begin_finalization(f.owner,f.capture)
        async with f.factory.begin() as db:
            row=await db.get(InterviewSchedule,f.interview)
            row.scheduled_at=f.now[0]-timedelta(days=1)
        with pytest.raises(TranscriptError,match='interview_window_closed'):
            await f.service.append_final(f.owner,event(f.capture))
        await f.service.append_final(f.owner,event(f.capture),finalizing=True)
        f.now[0]=deadline
        with pytest.raises(TranscriptError,match='finalization_window_closed'):
            await f.service.append_final(f.owner,event(f.capture,sequence=2),finalizing=True)
    run(pg,scenario)


def test_pg_caption_storage_failure_does_not_stop_temporary_captions(pg):
    from app.services.caption_transcript import CaptionTranscript
    from app.services.interview_captions import CaptionSession
    from unittest.mock import AsyncMock
    async def scenario(f):
        await start(f)
        runtime=N(storage=f.service,coordinator=N(_entries={f.interview:N(status='authorized_session_no_transcript',owner=f.owner,capture_id=f.capture)}))
        adapter=CaptionTranscript(runtime,f.interview)
        class Worker:
            async def start(self):pass
            async def close(self):pass
            async def transcribe(self,pcm):return 'Synthetic speech.'
        messages=[]
        async def send(value):messages.append(value)
        session=CaptionSession(Worker,storage=adapter)
        for role in ('recruiter','candidate'):await session.connect(role,send)
        await session.approve('recruiter');await session.approve('candidate')
        f.service.append_final=AsyncMock(side_effect=TranscriptError('transcript_storage_unavailable',outcome_uncertain=True))
        for _ in range(40):await session.audio('candidate',bytes(3200))
        assert not session.stopped and any(m['kind']=='caption' for m in messages)
        await session.stop()
        assert [m for m in messages if m['kind']=='storage'][-1]['status']=='unconfirmed'
    run(pg,scenario)


def test_pg_authenticated_consent_api_review_and_after_window_withdrawal(pg,monkeypatch):
    import httpx
    from app.main import app
    from app.api.routers import transcript_storage as api
    from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        authority=StorageConsentAuthority(f.factory,version=CONSENT_VERSION,clock=lambda:f.now[0])
        storage=TranscriptPersistenceService(f.factory,authority,clock=lambda:f.now[0])
        rt=N(authority=authority,storage=storage,privacy=TranscriptPrivacyService(storage),
            coordinator=TranscriptConsentCoordinator(authority,storage,enabled=True))
        monkeypatch.setattr(api,'runtime',lambda:rt)
        monkeypatch.setattr(api.settings,'transcript_storage_enabled',True)
        def headers(candidate=False):
            return {k.decode():v.decode() for k,v in f.request(candidate).scope['headers']}
        recruiter=f'/api/v1/jobs/{f.job}/interviews/{f.interview}'
        candidate='/api/v1/interview-access/transcript-storage'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            response=await client.post(recruiter+'/transcript-storage/prepare',json={},headers=headers())
            assert response.status_code==200
            capture=response.json()['capture_id']
            response=await client.post(candidate+'/prepare',json={},headers=headers(True))
            assert response.status_code==200 and response.json()['capture_id']==capture
            assert 'HttpOnly' in response.headers['set-cookie']
            for path,role in [(recruiter+'/transcript-storage/decision',False),(candidate+'/decision',True)]:
                h=headers(role);h['x-talenttrace-storage-consent']=CONSENT_VERSION
                response=await client.post(path,json={'capture_id':capture,'decision':'accept'},headers=h)
                assert response.status_code==200
            capture=__import__('uuid').UUID(capture)
            f.now[0]+=timedelta(seconds=10)
            await storage.append_final(f.owner,event(capture))
            response=await client.get(recruiter+'/transcript',headers=headers())
            assert response.status_code==200 and len(response.json()['turns'])==1
            assert (await client.get(recruiter+'/transcript',headers=headers(True))).status_code==401
            assert (await client.post(recruiter+'/transcript-storage/withdraw',json={})).status_code==403
            assert (await client.post(recruiter+'/transcript-storage/withdraw',json={},headers={'x-talenttrace-request':'1'})).status_code==401
            async with f.factory.begin() as db:
                row=await db.get(InterviewSchedule,f.interview);row.scheduled_at=datetime.now(timezone.utc)-timedelta(days=1)
                invitation=await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==f.interview))
                invitation.expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            # Only the dedicated privacy cookie is sent to this path; no join cookie needed.
            response=await client.post('/api/v1/interview-transcripts/privacy/withdraw',json={},headers={'x-talenttrace-request':'1'})
            assert response.status_code==200 and response.json()['deletion_verified']
            response=await client.get(recruiter+'/transcript',headers=headers())
            assert response.status_code==409 and response.json()['detail']['code']=='storage_authorization_revoked'
            assert (await client.get('/api/v1/interview-transcripts/privacy/status')).json()['deletion_verified']
    run(pg,scenario)


def test_pg_two_authenticated_websockets_consent_to_saved_review_to_deletion(pg,monkeypatch):
    from fastapi.testclient import TestClient
    from sqlalchemy.pool import NullPool
    from app.main import app
    from app.api.routers import transcript_storage as api, interview_captions as captions
    from app.services import transcript_runtime
    from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        # No connection is shared across the test HTTP/WebSocket event loops.
        engine=create_async_engine(pg,hide_parameters=True,poolclass=NullPool)
        factory=async_sessionmaker(engine,expire_on_commit=False)
        authority=StorageConsentAuthority(factory,version=CONSENT_VERSION,clock=lambda:f.now[0])
        storage=TranscriptPersistenceService(factory,authority,clock=lambda:f.now[0])
        rt=N(authority=authority,storage=storage,privacy=TranscriptPrivacyService(storage),
            coordinator=TranscriptConsentCoordinator(authority,storage,enabled=True))
        for module in (api,captions,transcript_runtime):monkeypatch.setattr(module,'runtime',lambda:rt)
        monkeypatch.setattr(captions,'session_factory',lambda:factory)
        monkeypatch.setattr(api.settings,'transcript_storage_enabled',True)
        monkeypatch.setattr(api.settings,'livekit_synthetic_demo_enabled',True)
        monkeypatch.setattr(api.settings,'environment','development')
        monkeypatch.setattr(api.settings,'local_caption_model_path',Path('synthetic-model-not-loaded'))
        class Worker:
            def __init__(self,*args):pass
            async def start(self):pass
            async def close(self):pass
            async def transcribe(self,pcm):
                f.now[0]+=timedelta(seconds=1)
                return 'Synthetic microphone speech.'
        monkeypatch.setattr(captions,'LocalWhisper',Worker)
        def headers(candidate=False):return {k.decode():v.decode() for k,v in f.request(candidate).scope['headers']}
        def rehearsal():
            with TestClient(app) as client:
                base=f'/api/v1/jobs/{f.job}/interviews/{f.interview}'
                candidate='/api/v1/interview-access/transcript-storage'
                first=client.post(base+'/transcript-storage/prepare',json={},headers=headers())
                second=client.post(candidate+'/prepare',json={},headers=headers(True))
                assert first.status_code==second.status_code==200
                capture=first.json()['capture_id'];assert capture==second.json()['capture_id']
                for path,role in [(base+'/transcript-storage/decision',False),(candidate+'/decision',True)]:
                    h=headers(role);h['x-talenttrace-storage-consent']=CONSENT_VERSION
                    assert client.post(path,json={'capture_id':capture,'decision':'accept'},headers=h).status_code==200
                rh=headers();ch=headers(True)
                rh['origin']=ch['origin']=api.settings.cors_origins[0]
                with client.websocket_connect(base+'/captions',headers=rh) as recruiter, client.websocket_connect('/api/v1/interview-access/captions',headers=ch) as candidate_socket:
                    assert recruiter.receive_json()['kind']=='waiting'
                    assert candidate_socket.receive_json()['kind']=='waiting'
                    recruiter.send_text('consent');candidate_socket.send_text('consent')
                    def until(socket,kind):
                        for _ in range(20):
                            value=socket.receive_json()
                            if value['kind']==kind:return value
                        raise AssertionError('Expected bounded protocol event missing')
                    until(recruiter,'active');until(candidate_socket,'active')
                    candidate_socket.send_bytes(bytes(3200))
                    # Wait until dispatch accepted this synthetic frame before ending.
                    for _ in range(100):
                        if captions.sessions[f.interview].frames['candidate']==1:break
                        time.sleep(.01)
                    recruiter.send_text('finish')
                    until(recruiter,'finishing');until(candidate_socket,'finishing')
                    recruiter.send_json({'kind':'end','frames':0,'samples':0,'captured_samples':0})
                    candidate_socket.send_json({'kind':'end','frames':1,'samples':1600,'captured_samples':1600})
                    assert until(recruiter,'storage')['status']=='saved'
                    until(recruiter,'stopped');until(candidate_socket,'stopped')
                review=client.get(base+'/transcript',headers=headers())
                assert review.status_code==200 and len(review.json()['turns'])==1
                assert review.json()['turns'][0]['role']=='candidate'
                assert review.json()['captures'][0]['status']=='completed'
                result=client.post('/api/v1/interview-transcripts/privacy/withdraw',json={},headers={'x-talenttrace-request':'1'})
                assert result.status_code==200 and result.json()['deletion_verified']
                assert client.get(base+'/transcript',headers=headers()).status_code==409
        try:await asyncio.to_thread(rehearsal)
        finally:
            captions.sessions.clear()
            await engine.dispose()
    run(pg,scenario)


def test_pg_restart_reconciliation_never_claims_recovered_audio_and_inactive_cleanup(pg):
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        privacy=TranscriptPrivacyService(f.service)
        await start(f);f.now[0]+=timedelta(seconds=10)
        await f.service.append_final(f.owner,event(f.capture))
        f.now[0]+=timedelta(minutes=11)
        await privacy.interrupt_stale()
        async with f.factory() as db:
            capture=await db.get(Capture,f.capture)
            assert capture.status=='interrupted' and capture.persistence_outcome=='partial'
            assert capture.capture_summary is None
        async with f.factory.begin() as db:
            user=await db.get(Recruiter,f.owner);user.active=False
        f.now[0]+=timedelta(days=31)
        result=await privacy.sweep()
        assert result['failed']==0
        async with f.factory() as db:
            assert await db.get(Capture,f.capture) is None
            assert (await db.get(InterviewSchedule,f.interview)).transcript_deletion_status=='deleted'
    run(pg,scenario)


def test_pg_storage_withdrawal_keeps_temporary_caption_stream_usable(pg):
    from app.services.caption_transcript import CaptionTranscript
    from app.services.interview_captions import CaptionSession
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        await start(f)
        rt=N(storage=f.service,coordinator=N(_entries={f.interview:N(status='authorized_session_no_transcript',owner=f.owner,capture_id=f.capture)}))
        class Worker:
            async def start(self):pass
            async def close(self):pass
            async def transcribe(self,pcm):return 'Temporary synthetic speech.'
        messages=[]
        async def send(value):messages.append(value)
        session=CaptionSession(Worker,storage=CaptionTranscript(rt,f.interview))
        for role in ('recruiter','candidate'):await session.connect(role,send)
        await session.approve('recruiter');await session.approve('candidate')
        assert (await TranscriptPrivacyService(f.service).withdraw(f.request(True),f.interview))['deletion_verified']
        for _ in range(40):await session.audio('candidate',bytes(3200))
        assert not session.stopped and any(m['kind']=='caption' for m in messages)
        await session.stop()
        async with f.factory() as db:
            assert await db.get(Capture,f.capture) is None
    run(pg,scenario)


def test_pg_failed_cleanup_does_not_starve_later_interviews(pg):
    from app.services.transcript_privacy import TranscriptPrivacyService
    from unittest.mock import AsyncMock
    async def scenario(f):
        other=await fixture(pg)
        try:
            await f.authority.withdraw(f.request(True),interview_id=f.interview)
            await other.authority.withdraw(other.request(True),interview_id=other.interview)
            privacy=TranscriptPrivacyService(f.service)
            privacy.delete_revoked=AsyncMock(side_effect=TranscriptError('transcript_storage_unavailable'))
            assert (await privacy.sweep(limit=1))['failed']==1
            first=privacy.delete_revoked.call_args.args[1]
            assert (await privacy.sweep(limit=1))['failed']==1
            second=privacy.delete_revoked.call_args.args[1]
            assert first!=second  # Bounded scan advances despite the earlier failure.
        finally:await other.engine.dispose()
    run(pg,scenario)


def test_pg_candidate_deletion_right_survives_owner_account_deactivation(pg):
    from app.services.transcript_privacy import TranscriptPrivacyService, PRIVACY_COOKIE
    async def scenario(f):
        await start(f)
        privacy=TranscriptPrivacyService(f.service)
        raw,_=await privacy.issue_candidate_access(f.request(True),f.interview)
        request=Request({'type':'http','method':'POST','headers':[
            (b'x-talenttrace-request',b'1'),(b'cookie',(PRIVACY_COOKIE+'='+raw).encode())]})
        async with f.factory.begin() as db:
            user=await db.get(Recruiter,f.owner);user.active=False
        assert (await privacy.withdraw(request,f.interview))['deletion_verified']
    run(pg,scenario)


def test_pg_stale_recovery_uses_recognition_start_not_delayed_consent_time(pg):
    from app.services.caption_transcript import CaptionTranscript
    from app.services.transcript_privacy import TranscriptPrivacyService
    async def scenario(f):
        await start(f);f.now[0]+=timedelta(minutes=9)
        rt=N(storage=f.service,coordinator=N(_entries={f.interview:N(status='authorized_session_no_transcript',owner=f.owner,capture_id=f.capture)}))
        adapter=CaptionTranscript(rt,f.interview);await adapter.start()
        assert adapter.capture==f.capture
        f.now[0]+=timedelta(minutes=2)
        privacy=TranscriptPrivacyService(f.service);await privacy.interrupt_stale()
        async with f.factory() as db:assert (await db.get(Capture,f.capture)).status=='active'
        f.now[0]+=timedelta(minutes=9)
        await privacy.interrupt_stale()
        async with f.factory() as db:assert (await db.get(Capture,f.capture)).status=='interrupted'
    run(pg,scenario)
