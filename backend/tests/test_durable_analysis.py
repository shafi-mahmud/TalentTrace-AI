import asyncio
import json
import subprocess
import sys
from datetime import timedelta
from uuid import uuid4
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.db.models.interview_analysis import InterviewAnalysis as Record
from app.services.durable_interview_analysis import DurableAnalysisManager
from app.services.evaluation_input import PostInterviewInputService
from app.agents.evaluation.workflow import InterviewEvaluationWorkflow
from app.rag.technical_references import CuratedTechnicalRetriever
from app.services.transcript_privacy import TranscriptPrivacyService
from test_interview_evaluation import FakeProvider
from test_interview_analysis_api import seeded
from test_interview_transcripts import pg,run,fixture


def manager(f,provider=None):return DurableAnalysisManager(PostInterviewInputService(f.service),InterviewEvaluationWorkflow(provider or FakeProvider(),CuratedTechnicalRetriever()),[f.job])


def test_pg_restart_independent_managers_deduplicate_and_delete(pg):
    async def scenario(f):
        await seeded(f);a,b=manager(f),manager(f);op=uuid4()
        try:
            first=await a.start(f.request(),f.job,f.interview,2,op)
            other=await b.start(f.request(),f.job,f.interview,2,uuid4())
            assert first['operation_id']==other['operation_id']
            await a.operations[op].task
            result=await manager(f).get(f.request(),f.job,f.interview,op)
            assert result['status']=='completed' and result['persistence']=='postgresql_privacy_bound'
            assert a.workflow.provider.calls==1 and b.workflow.provider.calls==0
            # A fresh interpreter has no access to either manager's Python memory.
            child='''
import asyncio,json,sys
sys.path.insert(0,'tests')
from uuid import UUID
from types import SimpleNamespace as N
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from starlette.requests import Request
from app.services.interview_transcripts import StorageConsentAuthority,TranscriptPersistenceService
from test_durable_analysis import manager
async def check():
    p=json.load(sys.stdin);engine=create_async_engine(p['url'],echo=False,hide_parameters=True)
    factory=async_sessionmaker(engine,expire_on_commit=False)
    service=TranscriptPersistenceService(factory,StorageConsentAuthority(factory,version='unused-read-only'))
    m=manager(N(service=service,job=UUID(p['job'])))
    try:
        request=Request({'type':'http','method':'GET','path':'/synthetic','headers':[(b'cookie',p['cookie'].encode())]})
        result=await m.get(request,UUID(p['job']),UUID(p['interview']),UUID(p['operation']))
        print(result['status'])
    finally:await m.close();await engine.dispose()
asyncio.run(check())
'''
            payload=dict(url=pg.render_as_string(hide_password=False),job=str(f.job),interview=str(f.interview),
                operation=str(op),cookie=f.request().headers['cookie'])
            process=await asyncio.to_thread(subprocess.run,[sys.executable,'-c',child],
                input=json.dumps(payload),capture_output=True,text=True,timeout=30)
            assert process.returncode==0,'Independent process could not read authorized durable result'
            assert process.stdout.strip()=='completed'
            await TranscriptPrivacyService(f.service).withdraw(f.request(),f.interview,f.job)
            from app.services.interview_transcripts import TranscriptError
            with pytest.raises((TranscriptError,HTTPException)):await b.get(f.request(),f.job,f.interview,op)
            async with f.factory() as db:assert await db.scalar(select(func.count()).select_from(Record).where(Record.interview_id==f.interview))==0
        finally:await a.close();await b.close()
    run(pg,scenario)


def test_pg_failed_provider_requires_explicit_fenced_retry(pg):
    async def scenario(f):
        await seeded(f);a=manager(f,FakeProvider(fail=True));op=uuid4()
        try:
            await a.start(f.request(),f.job,f.interview,2,op);await a.operations[op].task
            b=manager(f)
            try:
                failed=await b.get(f.request(),f.job,f.interview,op);assert failed['status']=='failed'
                assert (await b.start(f.request(),f.job,f.interview,2,op))['status']=='failed' and b.workflow.provider.calls==0
                with pytest.raises(HTTPException):await b.start(f.request(),f.job,f.interview,2,op,True,999)
                await b.start(f.request(),f.job,f.interview,2,op,True,1);await b.operations[op].task
                result=await b.get(f.request(),f.job,f.interview,op);assert result['status']=='completed' and result['attempt']==2
                assert b.workflow.provider.calls==1
            finally:await b.close()
        finally:await a.close()
    run(pg,scenario)


def test_pg_expired_claim_cannot_overwrite_restarted_worker(pg):
    async def scenario(f):
        await seeded(f);began,resume=asyncio.Event(),asyncio.Event()
        class Slow(FakeProvider):
            async def assess(self,*a,**k):
                began.set();await resume.wait();return await super().assess(*a,**k)
        a,b=manager(f,Slow()),manager(f);op=uuid4()
        try:
            await a.start(f.request(),f.job,f.interview,2,op);await began.wait()
            # Expire only the disposable fixture's claim, without changing source input.
            async with f.factory.begin() as db:
                row=await db.get(Record,op);row.lease_expires_at=f.now[0]-timedelta(seconds=1)
            failed=await b.get(f.request(),f.job,f.interview,op)
            assert failed['status']=='failed' and failed['error']=='evaluation_worker_interrupted'
            assert b.workflow.provider.calls==0
            await b.start(f.request(),f.job,f.interview,2,op,True,1)
            await b.operations[op].task
            resume.set();await a.operations[op].task
            result=await b.get(f.request(),f.job,f.interview,op)
            assert result['status']=='completed' and result['attempt']==2
            async with f.factory() as db:assert (await db.get(Record,op)).claim==b.operations[op].claim
        finally:
            resume.set();await a.close();await b.close()
    run(pg,scenario)


def test_pg_withdrawal_during_inference_blocks_durable_commit(pg):
    async def scenario(f):
        await seeded(f);began,resume=asyncio.Event(),asyncio.Event()
        class Slow(FakeProvider):
            async def assess(self,*a,**k):began.set();await resume.wait();return await super().assess(*a,**k)
        m=manager(f,Slow());op=uuid4()
        try:
            await m.start(f.request(),f.job,f.interview,2,op);await began.wait()
            await TranscriptPrivacyService(f.service).withdraw(f.request(),f.interview,f.job)
            resume.set();await m.operations[op].task
            async with f.factory() as db:assert await db.get(Record,op) is None
        finally:await m.close()
    run(pg,scenario)


def test_pg_cleanup_failure_denies_reads_until_verified_retry_and_isolates_other_interview(pg):
    async def scenario(f):
        from sqlalchemy import event
        from sqlalchemy.exc import OperationalError
        from app.services.interview_transcripts import TranscriptError
        other=await fixture(pg);a,b=manager(f),manager(other);op,second=uuid4(),uuid4()
        def fail_delete(connection,cursor,statement,parameters,context,many):
            if statement.startswith('DELETE FROM interview_analyses'):
                raise OperationalError('synthetic deletion failure',None,Exception('synthetic'))
        try:
            await seeded(f);await seeded(other)
            await a.start(f.request(),f.job,f.interview,2,op);await a.operations[op].task
            await b.start(other.request(),other.job,other.interview,2,second);await b.operations[second].task
            with pytest.raises((HTTPException,TranscriptError)):
                await a.get(other.request(),f.job,f.interview,op)
            event.listen(f.engine.sync_engine,'before_cursor_execute',fail_delete)
            try:
                status=await TranscriptPrivacyService(f.service).withdraw(f.request(),f.interview,f.job)
                assert status['withdrawn'] and status['deletion_status']=='failed' and not status['deletion_verified']
            finally:event.remove(f.engine.sync_engine,'before_cursor_execute',fail_delete)
            async with f.factory() as db:assert await db.get(Record,op) is not None
            with pytest.raises(TranscriptError):await manager(f).get(f.request(),f.job,f.interview,op)
            status=await TranscriptPrivacyService(f.service).withdraw(f.request(),f.interview,f.job)
            assert status['deletion_verified']
            assert (await b.get(other.request(),other.job,other.interview,second))['status']=='completed'
        finally:await a.close();await b.close();await other.engine.dispose()
    run(pg,scenario)


def test_pg_retention_expiry_denies_derived_reads_and_sweep_removes_result(pg):
    async def scenario(f):
        from app.services.interview_transcripts import TranscriptError
        from app.db.models.recruiter import InterviewSchedule
        await seeded(f);m=manager(f);op=uuid4()
        try:
            await m.start(f.request(),f.job,f.interview,2,op);await m.operations[op].task
            async with f.factory.begin() as db:
                row=await db.get(InterviewSchedule,f.interview)
                row.transcript_retention_deadline=f.now[0]-timedelta(seconds=1)
            with pytest.raises(TranscriptError):await m.get(f.request(),f.job,f.interview,op)
            result=await TranscriptPrivacyService(f.service).sweep()
            assert result['failed']==0
            async with f.factory() as db:assert await db.get(Record,op) is None
        finally:await m.close()
    run(pg,scenario)

def test_pg_uncertain_result_is_durable_and_withdrawal_deletes_it(pg):
    from app.db.models.interview_transcript import InterviewTranscriptTurn as Turn
    from app.services.interview_transcripts import TranscriptError
    async def scenario(f):
        await seeded(f)
        async with f.factory.begin() as db:
            turns=(await db.scalars(select(Turn).where(Turn.session_id==f.capture).order_by(Turn.sequence))).all()
            turns[0].text='are lists mutable.'
            turns[1].text='Lists can change.'
        provider=FakeProvider(fail=True);m=manager(f,provider);op=uuid4()
        try:
            await m.start(f.request(),f.job,f.interview,2,op)
            await m.operations[op].task
            result=await manager(f).get(f.request(),f.job,f.interview,op)
            assert result['status']=='completed' and result['result']['outcome']=='needs_review'
            assert result['result']['inference_performed'] is False and provider.calls==0
            assert result['result']['pairs'][0]['question_turns']
            status=await TranscriptPrivacyService(f.service).withdraw(f.request(),f.interview,f.job)
            assert status['deletion_verified']
            with pytest.raises((TranscriptError,HTTPException)):
                await manager(f).get(f.request(),f.job,f.interview,op)
        finally:await m.close()
    run(pg,scenario)
