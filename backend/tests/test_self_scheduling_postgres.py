import os,asyncio
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from sqlalchemy.engine import make_url
from app.db.models.recruiter import Recruiter,JobProfile,CandidateScoreRecord
from app.api.routers.self_scheduling import invite,book,slots,Selection,Booking,Capability
from app.api.routers.interviews import create_selected_interview
from app.schemas.interview import InterviewRequest
from app.schemas.candidate_score import ScoringWeights
from app.services.interview_slots import offered_slots
from fastapi import HTTPException
from test_candidate_scoring import scored

def test_real_postgres_booking_races(monkeypatch):
 url=os.environ.get('SELF_SCHEDULING_TEST_DATABASE_URL')
 if not url:pytest.skip('Dedicated disposable PostgreSQL required')
 u=make_url(url);assert u.database=='schedule_test' and u.port==54401
 fixtures=[scored(['supported'],weights=ScoringWeights(skill=100,experience=0,education=0)) for _ in range(6)]
 async def run():
  e=create_async_engine(url);f=async_sessionmaker(e,expire_on_commit=False);owner=uuid4();refs=[];raw=[];request=N(client=N(host='synthetic-test'))
  async with f() as s:
   s.add(Recruiter(id=owner,email=f'{owner}@example.test',password_hash='unused',active=True));await s.flush()
   for i in range(6):
    c,result,criteria=fixtures[i]
    j,b=uuid4(),uuid4();ref='TT-JOB-'+uuid4().hex[:16].upper();c=c.model_copy(update={'job_reference':ref})
    s.add(JobProfile(id=j,recruiter_id=owner,job_reference=ref,job_title='Synthetic',suggestions={},sources=[],confirmed_snapshot={'synthetic':True},revision=2,scoring_weights={'skill':100,'experience':0,'education':0}));await s.flush()
    s.add(CandidateScoreRecord(job_id=j,batch_id=b,upload_id=c.upload_id,criteria_revision=2,scoring_version='f2-coverage-v1',score=c.score,payload=c.model_dump(mode='json')));refs.append((j,b,c.upload_id))
   await s.commit()
  for j,b,c in refs:
   async with f() as s:raw.append((await invite(j,Selection(batch_id=b,upload_id=c,criteria_revision=2,selection_confirmed=True),N(id=owner),s))['token'])
  start=offered_slots()[0]
  async def attempt(index,manual=False):
   async with f() as s:
    try:
     if manual:
      j,b,c=refs[index];await create_selected_interview(j,InterviewRequest(batch_id=b,upload_id=c,criteria_revision=2,selection_confirmed=True,scheduled_at=start,timezone='Asia/Dhaka',duration_minutes=60),N(id=owner),s)
     else:await book(Booking(token=raw[index],scheduled_at=start),request,s)
     return 201
    except HTTPException as ex:await s.rollback();return ex.status_code
  first=await asyncio.gather(attempt(0),attempt(1));assert sorted(first)==[201,409]
  winner=first.index(201);assert await attempt(winner)==409
  async with f() as s:assert start not in (await slots(Capability(token=raw[2]),request,s))['slots']
  start=offered_slots()[1];assert sorted(await asyncio.gather(attempt(2),attempt(3,True)))==[201,409]
  from app.api.routers import interview_email as mail
  from app.services import interview_email as delivery
  import app.core.config as configuration
  from test_interview_email import config,Fake
  fake=Fake();cfg=config()
  monkeypatch.setattr(mail,'settings',cfg);monkeypatch.setattr(configuration,'settings',cfg)
  monkeypatch.setattr(delivery,'SMTPTransport',lambda:fake)
  j,b,c=refs[4];payload=mail.EmailSelection(batch_id=b,upload_id=c,criteria_revision=2,selection_confirmed=True,recipient='approved@synthetic.invalid')
  async with f() as s:
   result=await mail.send_scheduling_email(j,payload,N(id=owner),s)
   assert result=={'email_status':'accepted','reused':False}
  async with f() as s:
   repeated=await mail.send_scheduling_email(j,payload,N(id=owner),s)
   assert repeated=={'email_status':'accepted','reused':True} and len(fake.messages)==1
  from app.db.models.recruiter import SchedulingInvitation,InterviewEmailAttempt
  from sqlalchemy import select
  async with f() as s:
   cap=await s.scalar(select(SchedulingInvitation).where(SchedulingInvitation.job_id==j,SchedulingInvitation.revoked.is_(False)))
   # Send captures only in-memory template text; recover the fake transport link internally.
   token=fake.messages[0][-1].split('#schedule=',1)[1].split()[0]
   fake.error=TimeoutError('PRIVATE')
   confirmation=await book(Booking(token=token,scheduled_at=offered_slots()[2]),request,s)
   assert confirmation['email_status']=='uncertain'
  async with f() as s:
   consumed=await s.scalar(select(SchedulingInvitation).where(SchedulingInvitation.id==cap.id))
   assert consumed.interview_id==confirmation['interview'].id
   attempts=(await s.scalars(select(InterviewEmailAttempt).where(InterviewEmailAttempt.scheduling_invitation_id==consumed.id))).all()
   assert sorted(x.status for x in attempts)==['accepted','uncertain']
   assert all('token' not in x.__table__.columns for x in attempts)
  # Sender failures preserve booking; no second booking attempt is issued.
  await e.dispose()
 asyncio.run(run())
