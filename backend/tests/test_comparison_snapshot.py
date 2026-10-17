"""Real two-connection transactions: reproduce RC mixing and verify RR/privacy fencing."""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import os
import secrets
from uuid import uuid4
import httpx
import pytest
from fastapi import Depends
from sqlalchemy import select, delete, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from app.core.config import settings
from app.core.auth import database_session, token_hash
from app.db.models.recruiter import Recruiter, RecruiterSession, JobProfile, CandidateScoreRecord, InterviewSchedule
from app.db.models.interview_analysis import InterviewAnalysis as Analysis
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn
from app.services.evaluation_input import build_input
from app.services.interview_analysis import fingerprint
from app.agents.evaluation.workflow import InterviewEvaluationWorkflow
from app.api.routers.consolidated_assessment import snapshot_session
from test_consolidated_assessment import artifacts, add_interview
from test_candidate_comparison import path


@asynccontextmanager
async def committed_fixture(monkeypatch):
    if os.environ.get('F6_HOME_PG_TEST')!='1':pytest.skip('Opt in to isolated synthetic home PostgreSQL tests')
    url=make_url(settings.database_url.get_secret_value())
    assert url.host=='127.0.0.1' and url.port==5432 and (url.database=='talenttrace_home' or url.database.startswith('f6_test_'))
    engine=create_async_engine(url,echo=False,hide_parameters=True)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    a,b=await asyncio.to_thread(artifacts),await asyncio.to_thread(artifacts)
    owner=uuid4();token=secrets.token_urlsafe(32)
    b.parent.job_id=a.parent.job_id;b.snapshot=a.snapshot
    b.score=b.score.model_copy(update={'job_reference':a.snapshot['job_reference']})
    b.source=build_input(b.parent,b.snapshot,b.captures,b.turns);b.row.input_digest=fingerprint(b.source)
    for f in (a,b):f.factory,f.owner,f.now=factory,owner,f.captures[0].started_at
    try:
        async with factory.begin() as db:
            db.add(Recruiter(id=owner,email=f'{owner}@example.test',password_hash='unused-synthetic',active=True));await db.flush()
            db.add(RecruiterSession(token_hash=token_hash(token),recruiter_id=owner,expires_at=a.now+timedelta(hours=1)))
            db.add(JobProfile(id=a.parent.job_id,recruiter_id=owner,job_reference=a.snapshot['job_reference'],job_title=a.snapshot['job_title'],
                suggestions={'job_title':a.snapshot['job_title'],'criteria':a.snapshot['criteria']},sources=[],revision=2,
                confirmed_snapshot=a.snapshot,scoring_weights=a.score.weights.model_dump()));await db.flush()
            for f in (a,b):
                db.add(CandidateScoreRecord(job_id=a.parent.job_id,batch_id=f.parent.batch_id,upload_id=f.parent.upload_id,
                    criteria_revision=2,scoring_version='f2-coverage-v1',score=f.score.score,payload=f.score.model_dump(mode='json')))
        await add_interview(a);await add_interview(b)
        async def sessions():
            async with factory() as db:yield db
        monkeypatch.setitem(app.dependency_overrides,database_session,sessions)
        monkeypatch.setattr(settings,'transcript_storage_enabled',True)
        def forbidden(*args,**kwargs):raise AssertionError('No inference during comparison')
        monkeypatch.setattr(InterviewEvaluationWorkflow,'run',forbidden)
        from app.api.routers import interview_analysis
        monkeypatch.setattr(interview_analysis,'manager',forbidden)
        a.headers={'cookie':'talenttrace_session='+token}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            a.client=client
            yield a,b,factory
    finally:
        # Only random identities created here; no existing data/table/schema removed.
        async with factory.begin() as db:
            await db.execute(delete(Analysis).where(Analysis.interview_id.in_([a.parent.id,b.parent.id])))
            await db.execute(delete(Turn).where(Turn.session_id.in_([a.captures[0].id,b.captures[0].id])))
            await db.execute(delete(Capture).where(Capture.id.in_([a.captures[0].id,b.captures[0].id])))
            await db.execute(delete(InterviewSchedule).where(InterviewSchedule.id.in_([a.parent.id,b.parent.id])))
            await db.execute(delete(CandidateScoreRecord).where(CandidateScoreRecord.job_id==a.parent.job_id))
            await db.execute(delete(RecruiterSession).where(RecruiterSession.recruiter_id==owner))
            await db.execute(delete(JobProfile).where(JobProfile.id==a.parent.job_id))
            await db.execute(delete(Recruiter).where(Recruiter.id==owner))
        await engine.dispose()


@pytest.mark.parametrize('case',['repeatable_read','read_committed_control','withdrawal_conflict'])
def test_pg_concurrent_analysis_and_withdrawal(monkeypatch,case):
    async def scenario():
        async with committed_fixture(monkeypatch) as (a,b,factory):
            if case=='read_committed_control':
                async def rc(session=Depends(database_session)):return session
                monkeypatch.setitem(app.dependency_overrides,snapshot_session,rc)
            if case!='withdrawal_conflict':
                async with factory.begin() as db:
                    for identity in (a.row.id,b.row.id):
                        row=await db.get(Analysis,identity);row.status='failed';row.result=None
            from app.services import consolidated_assessment as service
            original=service.consolidated_assessment;updated=False;isolation=[];pids=[]
            async def reader(db,*args,**kwargs):
                nonlocal updated
                isolation.append(await db.scalar(text('SHOW transaction_isolation')))
                pids.append(await db.scalar(text('SELECT pg_backend_pid()')))
                result=await original(db,*args,**kwargs)
                if not updated:
                    updated=True
                    # A conforming F5/withdrawal writer locks only B's interview,
                    # not the job or A; it can commit between the two report reads.
                    async with factory.begin() as writer:
                        pids.append(await writer.scalar(text('SELECT pg_backend_pid()')))
                        interview=await writer.scalar(select(InterviewSchedule).where(InterviewSchedule.id==b.parent.id).with_for_update())
                        if case=='withdrawal_conflict':
                            interview.transcript_storage_revoked_at=b.now;interview.transcript_deletion_status='pending'
                        else:
                            row=await writer.get(Analysis,b.row.id);row.status='completed';row.result=b.row.result
                return result
            monkeypatch.setattr(service,'consolidated_assessment',reader)
            endpoint=path(a,(b.parent.batch_id,b.parent.upload_id))
            response=await a.client.get(endpoint,headers=a.headers)
            assert pids[0]!=pids[1], 'Writer must use a separate real connection'
            assert isolation[0]==('read committed' if case=='read_committed_control' else 'repeatable read')
            if case=='withdrawal_conflict':
                assert response.status_code==503,response.text
                assert 'ordered collection' not in response.text
            else:
                assert response.status_code==200,response.text
                states=[r['interview']['state'] for r in response.json()['reports']]
                assert states==(['unavailable','available'] if case=='read_committed_control' else ['unavailable','unavailable'])
            # A new request sees the committed update; no automatic retry/inference.
            fresh=await a.client.get(endpoint,headers=a.headers)
            assert fresh.status_code==200,fresh.text
            states=[r['interview']['state'] for r in fresh.json()['reports']]
            assert states==(['available','withdrawn'] if case=='withdrawal_conflict' else ['unavailable','available'])
            if case=='withdrawal_conflict':assert fresh.json()['reports'][1]['interview']['turns']==[]
    asyncio.run(scenario())
