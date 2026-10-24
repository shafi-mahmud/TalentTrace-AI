"""Connected Sprint 1-4 persistence/API acceptance; synthetic matcher and SMTP only."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace as N
from uuid import UUID, uuid4
import hashlib
import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.main import app
from app.core.auth import database_session, hash_password
from app.db.models.recruiter import Recruiter, JobProfile, InterviewSchedule, BookedInterviewEmailAttempt, InterviewInvitation
from app.schemas.batch_screening import ReviewedJobSnapshot, BatchScreeningItem, BatchScreeningResponse
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.services.screening_ranking import rank_eligible_candidates
from app.services.score_records import persist_scores
from app.services.recruiter_records import owned_job
from app.services import booked_interview_email as delivery
from app.api.routers import booked_interview_email as email_route, application_notifications as notification_route
from test_booked_email_postgres import disposable_pg
from test_booked_interview_email import imported_contact
from test_interview_email import config
from test_screening_decisions import scenario
from test_application_notifications import stored


def test_saved_job_eligible_application_reviewed_booking_and_email(disposable_pg,monkeypatch,tmp_path):
    async def run():
        engine=create_async_engine(disposable_pg,echo=False,hide_parameters=True);sessions=async_sessionmaker(engine,expire_on_commit=False)
        owner,foreign=uuid4(),uuid4();password='synthetic-connected-password-123'
        credentials=[('owner-'+owner.hex+'@example.test',owner),('foreign-'+foreign.hex+'@example.test',foreign)]
        async def database():
            async with sessions() as db:yield db
        previous=dict(app.dependency_overrides);app.dependency_overrides[database_session]=database
        monkeypatch.setattr(notification_route,'private_settings',lambda request:N(cv_upload_root=tmp_path/str(request.state.recruiter_id)))
        c=config();c.livekit_synthetic_demo_enabled=False;c.interview_public_origin=None;c.interview_email_recipients.append('other@synthetic.invalid')
        monkeypatch.setattr(email_route,'settings',c)
        class FakeSMTP:
            calls=0
            def send(self,*args):self.calls+=1
        fake=FakeSMTP();monkeypatch.setattr(delivery,'SMTPTransport',lambda:fake)
        async def denied(*args,**kwargs):raise AssertionError('External calls forbidden')
        monkeypatch.setattr(httpx.AsyncHTTPTransport,'handle_async_request',denied)
        def client():return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'X-TalentTrace-Request':'1','Origin':'http://test'})
        try:
            async with sessions.begin() as db:
                assert await db.scalar(text('SELECT version_num FROM alembic_version'))=='0017_booked_interview_email'
                for address,identity in credentials:db.add(Recruiter(id=identity,email=address,password_hash=hash_password(password),active=True))
            async with client() as recruiter,client() as other:
                for http,(address,_) in zip((recruiter,other),credentials):
                    assert (await http.post('/api/v1/auth/login',json={'email':address,'password':password})).status_code==200
                created=await recruiter.post('/api/v1/jobs',json={'job_title':'Synthetic connected appointment'})
                assert created.status_code==201;job_data=created.json();job_id=UUID(job_data['id']);reference=job_data['job_reference']
                second=(await recruiter.post('/api/v1/jobs',json={'job_title':'Synthetic separate job'})).json()
                supplied,matcher=scenario((('python','supported',True),))
                upload,batch_id=uuid4(),uuid4();supplied=supplied.model_copy(update={'job_reference':reference,'upload_id':upload})
                result=await CandidateScreeningWorkflow(matcher).screen(supplied)
                assert result.screening_decision=='eligible'
                reviewed=await recruiter.put(f'/api/v1/jobs/{job_id}/criteria',json={'revision':1,'criteria':[x.model_dump() for x in supplied.criteria],'confirmed':True,'weights':{'skill':100,'experience':0,'education':0}})
                assert reviewed.status_code==200 and reviewed.json()['revision']==2
                async with sessions() as db:
                    job=await owned_job(db,owner,job_id,lock=True)
                    snapshot=ReviewedJobSnapshot.model_validate(job.confirmed_snapshot)
                    batch=BatchScreeningResponse(job_reference=reference,batch_id=batch_id,snapshot=snapshot,processed_count=1,
                        candidates=[BatchScreeningItem(upload_id=upload,result=result,error_code=None,overall_coverage='met')],
                        ranking=rank_eligible_candidates([result],job_reference=reference,criteria=supplied.criteria))
                    scores=await persist_scores(db,job,batch)
                    assert scores.candidates[0].score==100 and scores.ranking[0].rank==1
                    contact=imported_contact(job,N(batch_id=batch_id,upload_id=upload),external_submission_id='connected-'+uuid4().hex)
                    stored(tmp_path/str(owner),reference,batch=batch_id,upload=upload)
                    data=(tmp_path/str(owner)/reference/str(batch_id)/(str(upload)+'.pdf')).read_bytes()
                    contact.size_bytes=len(data);contact.content_sha256=hashlib.sha256(data).hexdigest();db.add(contact);await db.commit()
                jobs=(await recruiter.get('/api/v1/jobs')).json();assert {j['id'] for j in jobs}=={str(job_id),second['id']}
                assert (await other.get('/api/v1/jobs')).json()==[]
                apps=f'/api/v1/jobs/{job_id}/applications'
                before=(await recruiter.get(apps)).json();assert before['received_count']==before['new_count']==1 and before['unavailable_count']==0
                assert (await other.get(apps)).status_code==404
                assert (await recruiter.get(f"/api/v1/jobs/{second['id']}/applications")).json()['received_count']==0
                ids=[{k:v[k] for k in ('batch_id','upload_id')} for v in before['applications']]
                assert (await recruiter.post(apps+'/viewed',json={'applications':ids})).status_code==204
                assert (await recruiter.get(apps)).json()['new_count']==0
                loaded=(await recruiter.get(f'/api/v1/jobs/{job_id}/batches/{batch_id}/scores')).json()
                assert loaded['candidates'][0]['screening_decision']=='eligible' and loaded['criteria_revision']==2
                start=datetime.now(timezone.utc).replace(second=0,microsecond=0)+timedelta(days=2)
                booking={'batch_id':str(batch_id),'upload_id':str(upload),'criteria_revision':2,'selection_confirmed':True,
                    'scheduled_at':start.isoformat(),'timezone':'Asia/Dhaka','duration_minutes':60}
                interviews=f'/api/v1/jobs/{job_id}/interviews'
                assert (await recruiter.post(interviews,json={**booking,'selection_confirmed':False})).status_code==422
                assert (await other.post(interviews,json=booking)).status_code==404
                saved=await recruiter.post(interviews,json=booking);assert saved.status_code==201
                interview=saved.json();assert interview['job_reference']==reference and interview['upload_id']==str(upload)
                assert (await recruiter.post(interviews,json=booking)).status_code==409
                path=interviews+'/'+interview['id']+'/appointment-email'
                assert (await recruiter.post(path+'/preview',json={'recipient':'other@synthetic.invalid'})).status_code==409
                preview=(await recruiter.post(path+'/preview',json={'recipient':'approved@synthetic.invalid'})).json()
                assert preview['contact_status']=='matches_recorded' and reference in preview['body'] and str(upload) in preview['body']
                assert '/interview-join' not in preview['body'] and 'no joining link' in preview['body']
                request={'recipient':'approved@synthetic.invalid','review_digest':preview['review_digest'],'confirmed':True}
                assert fake.calls==0
                assert (await recruiter.post(path,json=request)).json()=={'email_status':'accepted'}
                assert (await recruiter.post(path,json=request)).json()=={'email_status':'accepted'} and fake.calls==1
                # New authenticated client reloads from persisted data, not browser state.
                async with client() as reloaded:
                    assert (await reloaded.post('/api/v1/auth/login',json={'email':credentials[0][0],'password':password})).status_code==200
                    assert (await reloaded.get(path)).json()=={'email_status':'accepted'}
                    assert len((await reloaded.get(interviews)).json())==1
                    counts=(await reloaded.get(apps)).json();assert counts['received_count']==1 and counts['new_count']==0
                async with sessions() as db:
                    row=await db.get(InterviewSchedule,UUID(interview['id']))
                    assert (row.recruiter_id,row.job_id,row.batch_id,row.upload_id)==(owner,job_id,batch_id,upload)
                    assert row.screening_snapshot['screening_decision']=='eligible'
                    assert (await db.get(BookedInterviewEmailAttempt,row.id)).status=='accepted'
                    assert await db.scalar(select(InterviewInvitation).where(InterviewInvitation.interview_id==row.id)) is None
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(previous);await engine.dispose()
    asyncio.run(run())
