"""Owned persisted application discovery, using rollback-only synthetic records."""
import asyncio
from uuid import uuid4
import pytest
from sqlalchemy import select, delete, event
from app.db.models.recruiter import CandidateScoreRecord, InterviewSchedule
from app.db.models.external_cv import ExternalCvSubmissionRecord as Submission
from test_consolidated_assessment import home_fixture, add_interview
from test_candidate_comparison import second_application


async def ledger(f,batch=None,upload=None):
    async with f.factory.begin() as db:
        db.add(Submission(id=uuid4(),job_id=f.parent.job_id,source_job_reference=f.snapshot['job_reference'],
            source_id='synthetic-discovery',external_submission_id=uuid4().hex,batch_id=batch or uuid4(),upload_id=upload or uuid4(),
            file_type='pdf',size_bytes=100,content_sha256='a'*64,status='pending_review',application_email='not-for-discovery@example.test'))


@pytest.mark.parametrize('case',['scored','unscored','processing_failed','snapshot_only','historical_snapshot','historical_score',
    'withdrawn','invalid_snapshot','missing','ledger_only','ledger_dedup','different_job','foreign_job'])
def test_pg_discovery_states_and_read_only(monkeypatch,case):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            if case in {'snapshot_only','historical_snapshot','withdrawn','invalid_snapshot'}:await add_interview(f)
            if case in {'different_job','foreign_job'}:await second_application(f,other_job=True,foreign=case=='foreign_job')
            if case in {'ledger_only','ledger_dedup'}:await ledger(f,f.parent.batch_id if case=='ledger_dedup' else None,f.parent.upload_id if case=='ledger_dedup' else None)
            async with f.factory.begin() as db:
                row=await db.scalar(select(CandidateScoreRecord).where(CandidateScoreRecord.job_id==f.parent.job_id))
                if case in {'unscored','processing_failed'}:
                    row.score=None;row.payload=f.score.model_copy(update={'status':'not_evaluated','reason':'uncertain_evidence' if case=='unscored' else 'processing_failed',
                        'screening_decision':'eligible' if case=='unscored' else None,'score':None,'dimensions':()}).model_dump(mode='json')
                if case=='historical_score':row.criteria_revision=1
                if case in {'snapshot_only','historical_snapshot','missing','ledger_only'}:
                    await db.execute(delete(CandidateScoreRecord).where(CandidateScoreRecord.job_id==f.parent.job_id))
                if case=='historical_snapshot':
                    from app.db.models.recruiter import JobProfile
                    job=await db.get(JobProfile,f.parent.job_id);job.revision=3
                if case=='withdrawn':i=await db.get(InterviewSchedule,f.parent.id);i.transcript_storage_revoked_at=f.now
                if case=='invalid_snapshot':i=await db.get(InterviewSchedule,f.parent.id);i.screening_snapshot={'private':'must-not-appear'}
            statements=[]
            def sql(_conn,_cursor,statement,*args):statements.append(statement.strip().lower())
            event.listen(f.engine.sync_engine,'before_cursor_execute',sql)
            try:
                path=f'/api/v1/jobs/{f.parent.job_id}/assessment-applications'
                a=await f.client.get(path,headers=f.headers);b=await f.client.get(path,headers=f.headers)
            finally:event.remove(f.engine.sync_engine,'before_cursor_execute',sql)
            assert a.status_code==200,a.text
            assert a.json()==b.json() and a.headers['cache-control']=='no-store'
            rows=a.json()['applications']
            if case=='missing':assert rows==[]
            else:
                assert len(rows)==1
                r=rows[0]
                expected={'scored':'scored','unscored':'unscored','processing_failed':'unavailable','snapshot_only':'historical_snapshot',
                    'historical_snapshot':'historical_snapshot','withdrawn':'historical_snapshot','historical_score':'unavailable',
                    'invalid_snapshot':'unavailable','ledger_only':'unavailable','ledger_dedup':'scored','different_job':'scored','foreign_job':'scored'}[case]
                assert r['kind']==expected
                assert r['report_available']==(case not in {'historical_score','invalid_snapshot','ledger_only'})
                assert r['comparison_available']==(case not in {'historical_snapshot','historical_score','invalid_snapshot','ledger_only'})
                if case=='historical_score':assert r['recorded_revisions']==[1]
                if case=='historical_snapshot':assert r['evidence_revision']==2
                if case=='unscored':assert 'requirement-level matches were not retained' in r['detail']
            assert 'not-for-discovery@' not in a.text and 'ordered collection' not in a.text and 'must-not-appear' not in a.text
            assert not any(s.startswith(('insert ','update ','delete ')) for s in statements)
            if case=='withdrawn':
                r=await f.client.get(f.path,headers=f.headers)
                assert r.json()['interview']['state']=='withdrawn' and 'ordered collection' not in r.text
            if case in {'unscored','historical_snapshot','snapshot_only'}:
                r=await f.client.get(f.path,headers=f.headers)
                assert r.status_code==200
                assert r.json()['confirmed_requirements']==([] if case=='historical_snapshot' else f.snapshot['criteria'])
                if case=='unscored':assert r.json()['cv']['score'] is None and r.json()['cv']['dimensions']==[]
    asyncio.run(scenario())


def test_pg_discovery_access_and_bounds(monkeypatch):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            path=f'/api/v1/jobs/{f.parent.job_id}/assessment-applications'
            assert (await f.client.get(path)).status_code==401
            assert (await f.client.get(path,headers=f.foreign)).status_code==404
            assert (await f.client.get(path,headers={'cookie':'talenttrace_interview=synthetic'})).status_code==401
            await second_application(f)
            from app.services import assessment_discovery
            monkeypatch.setattr(assessment_discovery,'MAX_APPLICATIONS',1)
            r=await f.client.get(path,headers=f.headers)
            assert r.status_code==409 and 'applications' not in r.json()
    asyncio.run(scenario())


def test_pg_snapshot_only_current_application_is_comparable(monkeypatch):
    async def scenario():
        async with home_fixture(monkeypatch) as f:
            await add_interview(f);second=await second_application(f)
            async with f.factory.begin() as db:
                await db.execute(delete(CandidateScoreRecord).where(CandidateScoreRecord.job_id==f.parent.job_id,CandidateScoreRecord.upload_id==f.parent.upload_id))
            from test_candidate_comparison import path
            r=await f.client.get(path(f,second),headers=f.headers)
            assert r.status_code==200 and r.json()['reports'][0]['cv_source']=='interview_selection_snapshot'
    asyncio.run(scenario())
