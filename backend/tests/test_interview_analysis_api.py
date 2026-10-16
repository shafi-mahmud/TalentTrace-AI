import asyncio
from uuid import uuid4,UUID
import httpx
import pytest
from sqlalchemy import select,func
from fastapi import HTTPException
from app.main import app
from app.db.models.interview_transcript import InterviewTranscriptTurn as Turn
from app.db.models.recruiter import InterviewSchedule
from app.services.evaluation_input import PostInterviewInputService
from app.services.interview_analysis import AnalysisManager,DISCLOSURE_VERSION
from app.services.interview_mapping import SyntheticTechnicalRetriever
from app.agents.evaluation.workflow import InterviewEvaluationWorkflow
from app.api.routers import interview_analysis as api
from app.services.transcript_privacy import TranscriptPrivacyService
from test_interview_evaluation import FakeProvider
from test_evaluation_input import completed
from test_interview_transcripts import pg,run,fixture


async def seeded(f):
    await completed(f)
    async with f.factory.begin() as db:
        turns=(await db.scalars(select(Turn).where(Turn.session_id==f.capture).order_by(Turn.sequence))).all()
        turns[0].text='In Python, are lists mutable?'
        turns[1].text='Python lists are immutable.'


def headers(f,candidate=False):
    h={k.decode():v.decode() for k,v in f.request(candidate).scope['headers']}
    return {**h,'x-talenttrace-evaluation-disclosure':DISCLOSURE_VERSION,'x-talenttrace-job-revision':'2'}


def manager(f,provider=None):
    return AnalysisManager(PostInterviewInputService(f.service),
        InterviewEvaluationWorkflow(provider or FakeProvider(),SyntheticTechnicalRetriever()),[f.job])


def test_pg_actual_api_graph_results_idempotency_and_deletion_fence(pg,monkeypatch):
    async def scenario(f):
        await seeded(f);m=manager(f)
        monkeypatch.setattr(api,'available',lambda:True);monkeypatch.setattr(api,'manager',lambda:m)
        path=f'/api/v1/jobs/{f.job}/interviews/{f.interview}/analysis';op=uuid4()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
            try:
                assert (await client.post(path,json={'operation_id':str(op)})).status_code in {403,422}
                response=await client.post(path,json={'operation_id':str(op)},headers=headers(f))
                assert response.status_code==202 and response.headers['cache-control']=='no-store'
                await m.operations[op].task
                response=await client.get(path+'/'+str(op),headers=headers(f))
                assert response.status_code==200 and response.json()['status']=='completed'
                result=response.json()['result'];assert result['provider']=='mock' and result['pairs'] and result['requirements']
                assert len(result['assessment']['answers'][0]['dimensions'])==4
                response=await client.post(path,json={'operation_id':str(op)},headers=headers(f))
                assert response.json()['status']=='completed' and m.workflow.provider.calls==1
                response=await client.post(path,json={'operation_id':str(uuid4())},headers=headers(f))
                assert response.json()['operation_id']==str(op) and m.workflow.provider.calls==1
                assert (await client.get(path+'/'+str(op),headers=headers(f,True))).status_code==401
                other=await fixture(pg)
                try:assert (await client.get(path+'/'+str(op),headers=headers(other))).status_code==409
                finally:await other.engine.dispose()
                assert m.operations[op].result is not None
                await TranscriptPrivacyService(f.service).withdraw(f.request(),f.interview,f.job)
                response=await client.get(path+'/'+str(op),headers=headers(f))
                assert response.status_code==409 and m.operations[op].result is None
                async with f.factory() as db:
                    assert await db.scalar(select(func.count()).select_from(Turn).where(Turn.session_id==f.capture))==0
            finally:await m.close()
    run(pg,scenario)


def test_pg_withdrawal_during_model_call_never_reveals_result(pg):
    async def scenario(f):
        await seeded(f);began,resume=asyncio.Event(),asyncio.Event()
        class Slow(FakeProvider):
            async def assess(self,*args,**kwargs):
                began.set();await resume.wait();return await super().assess(*args,**kwargs)
        m=manager(f,Slow());request=f.request();op=uuid4()
        try:
            await m.start(request,f.job,f.interview,2,op);await began.wait()
            await TranscriptPrivacyService(f.service).withdraw(request,f.interview,f.job)
            resume.set();await m.operations[op].task
            assert m.operations[op].state=='failed' and m.operations[op].result is None
        finally:await m.close()
    run(pg,scenario)


@pytest.mark.parametrize('kind',['expired','partial','failed_provider','revision','allowlist'])
def test_pg_failure_states_and_explicit_recovery(pg,kind):
    async def scenario(f):
        await seeded(f);m=manager(f,FakeProvider(fail=kind=='failed_provider'));op=uuid4()
        if kind in {'expired','partial'}:
            async with f.factory.begin() as db:
                row=await db.get(InterviewSchedule,f.interview)
                if kind=='expired':row.transcript_retention_deadline=f.now[0]
                else:
                    from app.db.models.interview_transcript import InterviewTranscriptSession
                    c=await db.get(InterviewTranscriptSession,f.capture);c.status='interrupted';c.persistence_outcome='partial'
        if kind=='allowlist':m.allowed_jobs=set()
        try:
            if kind=='failed_provider':
                await m.start(f.request(),f.job,f.interview,2,op);await m.operations[op].task
                assert m.operations[op].state=='failed' and not m.operations[op].result
                assert m.workflow.provider.calls==1
            else:
                from app.services.interview_transcripts import TranscriptError
                from app.services.evaluation_input import EvaluationInputError
                with pytest.raises((HTTPException,TranscriptError,EvaluationInputError)):
                    await m.start(f.request(),f.job,f.interview,3 if kind=='revision' else 2,op)
                assert not m.operations
        finally:await m.close()
    run(pg,scenario)


def test_disabled_route_no_model_call(monkeypatch):
    monkeypatch.setattr(api,'available',lambda:False)
    with pytest.raises(HTTPException):api.active_manager()
