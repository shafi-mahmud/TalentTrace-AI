"""Same-job comparison reuses the report privacy boundary; synthetic rollback fixtures."""
import asyncio
from uuid import uuid4
import pytest
from sqlalchemy import select, event
from app.db.models.recruiter import CandidateScoreRecord, JobProfile, RecruiterSession, InterviewSchedule
from app.db.models.interview_analysis import InterviewAnalysis as Analysis
from app.db.models.interview_transcript import InterviewTranscriptTurn as Turn
from app.core.auth import token_hash
from test_consolidated_assessment import home_fixture, add_interview


async def second_application(f,other_job=False,foreign=False):
    batch,upload=uuid4(),uuid4();job=f.parent.job_id;reference=f.snapshot['job_reference']
    async with f.factory.begin() as db:
        if other_job:
            owner=f.owner
            if foreign:
                token=f.foreign['cookie'].split('=',1)[1]
                owner=await db.scalar(select(RecruiterSession.recruiter_id).where(RecruiterSession.token_hash==token_hash(token)))
            job=uuid4();reference='TT-JOB-'+uuid4().hex[:16].upper()
            snapshot={**f.snapshot,'job_reference':reference}
            db.add(JobProfile(id=job,recruiter_id=owner,job_reference=reference,job_title=snapshot['job_title'],
                revision=2,confirmed_snapshot=snapshot,suggestions={'job_title':snapshot['job_title'],'criteria':snapshot['criteria']},
                sources=[],scoring_weights=f.score.weights.model_dump()));await db.flush()
        score=f.score.model_copy(update={'upload_id':upload,'job_reference':reference})
        db.add(CandidateScoreRecord(job_id=job,batch_id=batch,upload_id=upload,criteria_revision=2,
            scoring_version='f2-coverage-v1',score=score.score,payload=score.model_dump(mode='json')))
    return batch,upload


def path(f,second):
    return f'/api/v1/jobs/{f.parent.job_id}/assessment-comparison?left_batch={f.parent.batch_id}&left_upload={f.parent.upload_id}&right_batch={second[0]}&right_upload={second[1]}'


@pytest.mark.parametrize('case',['cv_only','complete','missing_analysis','withdrawn','expired','deleted','source_changed','ambiguous'])
def test_pg_same_job_privacy_and_read_only_reload(monkeypatch,case):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            second=await second_application(f)
            if case!='cv_only':await add_interview(f,analysis=case!='missing_analysis')
            async with f.factory.begin() as db:
                i=await db.get(InterviewSchedule,f.parent.id)
                if case=='withdrawn':i.transcript_storage_revoked_at=f.now
                if case=='expired':i.transcript_retention_deadline=f.now
                if case=='deleted':i.transcript_deletion_status='deleted';i.transcript_deleted_at=f.now
                if case=='source_changed':t=await db.get(Turn,f.turns[1].id);t.text='Other synthetic source.'
                if case=='ambiguous':
                    old=await db.get(Analysis,f.row.id)
                    db.add(Analysis(id=uuid4(),interview_id=i.id,recruiter_id=f.owner,job_id=i.job_id,
                        input_digest=old.input_digest,criteria_revision=2,rubric_version=old.rubric_version,provider='mock',model='another',
                        corpus_version=old.corpus_version,status='completed',attempt=1,claim=uuid4(),lease_expires_at=old.lease_expires_at,
                        created_at=f.now,updated_at=f.now,result=old.result))
            statements=[]
            def sql(_conn,_cursor,statement,*args):statements.append(statement.strip().lower())
            event.listen(f.engine.sync_engine,'before_cursor_execute',sql)
            try:
                a=await f.client.get(path(f,second),headers=f.headers)
                b=await f.client.get(path(f,second),headers=f.headers)
            finally:event.remove(f.engine.sync_engine,'before_cursor_execute',sql)
            assert a.status_code==200,a.text
            assert a.json()==b.json() and a.headers['cache-control']=='no-store'
            value=a.json();left,right=value['reports'];assert value['job_id']==str(f.parent.job_id)
            assert left['upload_id']==str(f.parent.upload_id) and right['upload_id']==str(second[1])
            assert right['interview']['state']=='not_scheduled'
            expected={'cv_only':'not_scheduled','complete':'available','source_changed':'stale'}.get(case,case)
            assert left['interview']['state']==expected
            if expected!='available':assert left['interview']['turns']==[] and 'ordered collection' not in a.text
            assert not any(s.startswith(('insert ','update ','delete ')) for s in statements)
    asyncio.run(scenario())


@pytest.mark.parametrize('case',['duplicate','different_job','foreign_application','foreign_recruiter','anonymous','candidate','wrong_batch','revision','weights','unconfirmed'])
def test_pg_comparison_selection_denial(monkeypatch,case):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            second=await second_application(f,other_job=case in {'different_job','foreign_application'},foreign=case=='foreign_application')
            headers=f.headers;expected=404
            if case=='duplicate':second=(f.parent.batch_id,f.parent.upload_id);expected=422
            if case=='foreign_recruiter':headers=f.foreign
            if case=='anonymous':headers={};expected=401
            if case=='candidate':headers={'cookie':'talenttrace_interview=synthetic-candidate-cookie'};expected=401
            if case=='wrong_batch':second=(uuid4(),second[1])
            if case=='unconfirmed':
                async with f.factory.begin() as db:
                    job=await db.get(JobProfile,f.parent.job_id);job.confirmed_snapshot=None
                expected=409
            if case in {'revision','weights'}:
                await add_interview(f)
                async with f.factory.begin() as db:
                    if case=='revision':
                        job=await db.get(JobProfile,f.parent.job_id);job.revision=3
                        row=await db.scalar(select(CandidateScoreRecord).where(CandidateScoreRecord.upload_id==second[1]));row.criteria_revision=3
                    else:
                        interview=await db.get(InterviewSchedule,f.parent.id)
                        interview.screening_snapshot=f.score.model_copy(update={'status':'not_evaluated','reason':'uncertain_evidence','score':None,'dimensions':(),
                            'weights':f.score.weights.model_copy(update={'skill':50,'experience':30,'education':20})}).model_dump(mode='json')
                expected=409
            r=await f.client.get(path(f,second),headers=headers)
            assert r.status_code==expected,r.text
            assert 'ordered collection' not in r.text and 'Synthetic persisted' not in r.text
    asyncio.run(scenario())


def test_pg_expiry_during_pair_retrieval_is_redacted(monkeypatch):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            await add_interview(f);second=await second_application(f)
            from app.services import consolidated_assessment as service
            # Initial source gate uses the storage clock. Advance the final pair
            # guard to the retention boundary to simulate elapsed retrieval time.
            monkeypatch.setattr(service,'utc_now',lambda:f.parent.transcript_retention_deadline)
            r=await f.client.get(path(f,second),headers=f.headers)
            assert r.status_code==200 and r.json()['reports'][0]['interview']['state']=='expired'
            assert 'ordered collection' not in r.text
    asyncio.run(scenario())
