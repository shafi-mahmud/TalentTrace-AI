"""Synthetic F6 tests; optional PostgreSQL fixtures are entirely rolled back."""
import asyncio
from contextlib import asynccontextmanager
from datetime import timedelta
import os
import secrets
from types import SimpleNamespace as N
from uuid import uuid4
import httpx
import pytest
from sqlalchemy import select, event, delete, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from app.core.auth import database_session, token_hash
from app.core.config import settings
from app.db.models.recruiter import Recruiter, RecruiterSession, JobProfile, CandidateScoreRecord, InterviewSchedule
from app.db.models.interview_transcript import InterviewTranscriptSession as Capture, InterviewTranscriptTurn as Turn
from app.db.models.interview_analysis import InterviewAnalysis as Analysis
from app.services.evaluation_input import build_input
from app.services.interview_analysis import fingerprint
from app.services.interview_qa import pair_transcript
from app.services.interview_mapping import map_requirements
from app.agents.evaluation.workflow import RUBRIC_VERSION, ModelAssessment, InterviewEvaluationWorkflow, AssessmentError
from app.services.consolidated_assessment import checked_result
from app.schemas.candidate_score import ScoringWeights
from test_candidate_scoring import scored
from test_evaluation_input import source


def artifacts():
    p,s,c,t=source();s['job_reference']='TT-JOB-'+uuid4().hex[:16].upper()
    score,_,criteria=scored(['supported'],weights=ScoringWeights(skill=100,experience=0,education=0))
    s['criteria']=[v.model_dump(mode='json') for v in criteria]
    score=score.model_copy(update={'job_reference':s['job_reference'],'upload_id':p.upload_id})
    data=build_input(p,s,c,t);pairs=pair_transcript(data)
    assessment=ModelAssessment.model_validate({'answers':[{'qa_id':v.id,'dimensions':[
        {'dimension':d,'status':'supported' if d=='relevance' else 'uncertain','justification':'Synthetic persisted interpretation.',
         'evidence':[{'turn_id':t[1].id,'quote':'ordered collection'}] if d=='relevance' else []}
        for d in ('relevance','technical_accuracy','completeness','articulation')],
        'technical_citations':[],'follow_up':'Verify with a concrete example.'} for v in pairs]})
    result={'rubric_version':RUBRIC_VERSION,'criteria_revision':2,'advisory':True,'scope':data.scope,'asr_review':data.asr_review,
        'pairs':[v.model_dump(mode='json') for v in pairs],'turns':[v.model_dump(mode='json') for v in data.turns],
        'requirements':[v.model_dump(mode='json') for v in map_requirements(data,pairs)],'technical_references':[],
        'assessment':assessment.model_dump(mode='json')}
    row=N(id=uuid4(),input_digest=fingerprint(data),rubric_version=RUBRIC_VERSION,result=result)
    return N(parent=p,snapshot=s,captures=c,turns=t,score=score,source=data,row=row)


def test_projection_revalidates_quotes():
    f=artifacts();assert checked_result(f.row,f.source).assessment.answers[0].dimensions[0].status=='supported'
    f.row.result['assessment']['answers'][0]['dimensions'][0]['evidence'][0]['quote']='fabricated'
    with pytest.raises(AssessmentError):checked_result(f.row,f.source)
    f=artifacts();f.row.result['pairs'][0]['start_ms']=999
    with pytest.raises(ValueError):checked_result(f.row,f.source)


@pytest.mark.parametrize('change',['digest','turn','coverage','revision'])
def test_tampered_result_rejected(change):
    f=artifacts()
    if change=='digest':f.row.input_digest='0'*64
    if change=='turn':f.row.result['turns'][1]['text']='fabricated'
    if change=='coverage':f.row.result['requirements'][0]['coverage']='partial'
    if change=='revision':f.row.result['criteria_revision']=3
    with pytest.raises(ValueError):checked_result(f.row,f.source)


@asynccontextmanager
async def home_fixture(monkeypatch):
    if os.environ.get('F6_HOME_PG_TEST')!='1':pytest.skip('Opt in to rollback-only home PostgreSQL tests')
    from sqlalchemy.engine import make_url
    url=make_url(settings.database_url.get_secret_value())
    assert (url.host,url.port,url.database)==('127.0.0.1',5432,'talenttrace_home'),'Explicit synthetic home DB required'
    engine=create_async_engine(url,echo=False,hide_parameters=True)
    f=await asyncio.to_thread(artifacts);owner,foreign=uuid4(),uuid4();cookie,other=secrets.token_urlsafe(32),secrets.token_urlsafe(32)
    now=f.captures[0].started_at
    try:
        async with engine.connect() as conn:
            outer=await conn.begin()
            factory=async_sessionmaker(conn,expire_on_commit=False,join_transaction_mode='create_savepoint')
            try:
                async with factory.begin() as db:
                    for uid,token in ((owner,cookie),(foreign,other)):
                        db.add(Recruiter(id=uid,email=f'{uid}@example.test',password_hash='unused-synthetic',active=True));await db.flush()
                        db.add(RecruiterSession(token_hash=token_hash(token),recruiter_id=uid,expires_at=now+timedelta(hours=1)))
                    db.add(JobProfile(id=f.parent.job_id,recruiter_id=owner,job_reference=f.snapshot['job_reference'],job_title=f.snapshot['job_title'],
                        suggestions={'job_title':f.snapshot['job_title'],'criteria':f.snapshot['criteria']},sources=[],revision=2,
                        confirmed_snapshot=f.snapshot,scoring_weights=f.score.weights.model_dump()));await db.flush()
                    db.add(CandidateScoreRecord(job_id=f.parent.job_id,batch_id=f.parent.batch_id,upload_id=f.parent.upload_id,
                        criteria_revision=2,scoring_version='f2-coverage-v1',score=f.score.score,payload=f.score.model_dump(mode='json')))
                async def sessions():
                    async with factory() as db:yield db
                monkeypatch.setitem(app.dependency_overrides,database_session,sessions)
                from app.api.routers.consolidated_assessment import snapshot_session
                from fastapi import Depends
                async def bound_snapshot(session=Depends(database_session)):
                    return session
                monkeypatch.setitem(app.dependency_overrides,snapshot_session,bound_snapshot)
                monkeypatch.setattr(settings,'transcript_storage_enabled',True)
                def forbidden(*a,**kw):raise AssertionError('Report must not run inference')
                monkeypatch.setattr(InterviewEvaluationWorkflow,'run',forbidden)
                from app.api.routers import interview_analysis
                monkeypatch.setattr(interview_analysis,'manager',forbidden)
                f.factory,f.owner,f.now,f.engine=factory,owner,now,engine
                f.path=f'/api/v1/jobs/{f.parent.job_id}/batches/{f.parent.batch_id}/candidates/{f.parent.upload_id}/assessment'
                f.headers={'cookie':'talenttrace_session='+cookie};f.foreign={'cookie':'talenttrace_session='+other}
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
                    f.client=client;yield f
            finally:
                await outer.rollback()
                assert await conn.scalar(select(func.count()).select_from(Recruiter).where(Recruiter.id==owner))==0
    finally:await engine.dispose()


async def add_interview(f,analysis=True):
    async with f.factory.begin() as db:
        p=f.parent
        db.add(InterviewSchedule(id=p.id,recruiter_id=f.owner,job_id=p.job_id,batch_id=p.batch_id,upload_id=p.upload_id,
            criteria_revision=2,scoring_version='f2-coverage-v1',scheduled_at=f.now,timezone='Asia/Dhaka',duration_minutes=60,
            unscored_confirmed=False,screening_snapshot=f.score.model_dump(mode='json'),transcript_retention_deadline=p.transcript_retention_deadline));await db.flush()
        c=f.captures[0]
        db.add(Capture(**{k:getattr(c,k) for k in ('id','interview_id','started_at','ended_at','recruiter_consented_at',
            'candidate_consented_at','consent_version','status','persistence_outcome','capture_summary')}));await db.flush()
        for t in f.turns:db.add(Turn(**vars(t),created_at=f.now))
        if analysis:db.add(Analysis(id=f.row.id,interview_id=p.id,recruiter_id=f.owner,job_id=p.job_id,input_digest=f.row.input_digest,
            criteria_revision=2,rubric_version=RUBRIC_VERSION,provider='mock',model='synthetic',corpus_version='synthetic-v1',status='completed',
            attempt=1,claim=uuid4(),lease_expires_at=f.now+timedelta(minutes=5),created_at=f.now,updated_at=f.now,result=f.row.result))


@pytest.mark.parametrize('case',['complete','cv_only','snapshot_only','missing_analysis','withdrawn','expired','deleted',
    'pending','failed','disabled','stale','tampered','unsupported_consent','rerun_replaced','source_changed','ambiguous'])
def test_pg_evidence_states(monkeypatch,case):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            if case!='cv_only':await add_interview(f,analysis=case!='missing_analysis')
            async with f.factory.begin() as db:
                i=await db.get(InterviewSchedule,f.parent.id);row=await db.get(Analysis,f.row.id)
                if case=='snapshot_only':await db.execute(delete(CandidateScoreRecord).where(CandidateScoreRecord.job_id==f.parent.job_id))
                if case=='rerun_replaced':
                    cvrow=await db.scalar(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id==f.parent.job_id))
                    cvrow.score=None;cvrow.payload=f.score.model_copy(update={'status':'not_evaluated','reason':'uncertain_evidence','score':None,'dimensions':()}).model_dump(mode='json')
                if case=='withdrawn':i.transcript_storage_revoked_at=f.now
                if case=='expired':i.transcript_retention_deadline=f.now-timedelta(seconds=1)
                if case=='deleted':i.transcript_deletion_status='deleted';i.transcript_deleted_at=f.now
                if case=='pending':row.status='running';row.result=None
                if case=='failed':row.status='failed';row.result=None
                if case=='disabled':monkeypatch.setattr(settings,'transcript_storage_enabled',False)
                if case=='stale':job=await db.get(JobProfile,f.parent.job_id);job.revision=3
                if case=='tampered':value=dict(row.result);value['criteria_revision']=3;row.result=value
                if case=='unsupported_consent':c=await db.get(Capture,f.captures[0].id);c.consent_version='unapproved-version'
                if case=='source_changed':t=await db.get(Turn,f.turns[1].id);t.text='Different synthetic source.'
                if case=='ambiguous':db.add(Analysis(id=uuid4(),interview_id=i.id,recruiter_id=f.owner,job_id=i.job_id,input_digest=row.input_digest,
                    criteria_revision=2,rubric_version=RUBRIC_VERSION,provider='mock',model='other',corpus_version='synthetic-v1',status='completed',
                    attempt=1,claim=uuid4(),lease_expires_at=row.lease_expires_at,created_at=f.now,updated_at=f.now,result=row.result))
            statements=[]
            def sql(_conn,_cursor,statement,*args):statements.append(statement.strip().lower())
            event.listen(f.engine.sync_engine,'before_cursor_execute',sql)
            try:
                a=await f.client.get(f.path,headers=f.headers);b=await f.client.get(f.path,headers=f.headers)
            finally:event.remove(f.engine.sync_engine,'before_cursor_execute',sql)
            assert a.status_code==200,a.text
            assert a.json()==b.json() and a.headers['cache-control']=='no-store'
            expected={'complete':'available','cv_only':'not_scheduled','snapshot_only':'available','tampered':'unavailable',
                'unsupported_consent':'unavailable','rerun_replaced':'available','source_changed':'stale','failed':'unavailable'}.get(case,case)
            value=a.json();assert value['interview']['state']==expected
            assert value['confirmed_requirements']==([] if case=='stale' else f.snapshot['criteria'])
            assert value['cv']['score']==100 and value['review_required'] is True
            if expected!='available':
                assert value['interview']['assessment'] is None and value['interview']['turns']==[]
                assert 'ordered collection' not in a.text
            else:assert value['interview']['assessment']['answers'][0]['dimensions'][0]['status']=='supported'
            assert not any(s.startswith(('insert ','update ','delete ')) for s in statements)
    asyncio.run(scenario())


@pytest.mark.parametrize('case',['current','historical','unconfirmed','invalid','wrong_job','wrong_category'])
def test_requirement_names_use_only_matching_confirmed_revision(case):
    from copy import deepcopy
    from app.services.consolidated_assessment import report_requirements
    f=artifacts();job=N(revision=2,job_reference=f.snapshot['job_reference'],confirmed_snapshot=deepcopy(f.snapshot))
    revision=1 if case=='historical' else 2
    if case=='unconfirmed':job.confirmed_snapshot=None
    if case=='invalid':job.confirmed_snapshot={'criteria':'not a snapshot'}
    if case=='wrong_job':job.job_reference='TT-JOB-FFFFFFFFFFFFFFFF'
    if case=='wrong_category':job.confirmed_snapshot['criteria'][0]['category']='education'
    result=report_requirements(job,revision,f.score)
    assert [r.model_dump() for r in result]==(f.snapshot['criteria'] if case=='current' else [])


def test_pg_auth_identity_invalid_snapshot(monkeypatch):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            assert (await f.client.get(f.path)).status_code==401
            assert (await f.client.get(f.path,headers={'cookie':'talenttrace_interview='+secrets.token_urlsafe(32)})).status_code==401
            assert (await f.client.get(f.path,headers=f.foreign)).status_code==404
            for identity in (f.parent.upload_id,f.parent.batch_id):
                assert (await f.client.get(f.path.replace(str(identity),str(uuid4())),headers=f.headers)).status_code==404
            await add_interview(f)
            async with f.factory.begin() as db:
                row=await db.get(InterviewSchedule,f.parent.id);row.screening_snapshot={}
            r=await f.client.get(f.path,headers=f.headers)
            assert r.status_code==409 and 'ordered collection' not in r.text
    asyncio.run(scenario())
