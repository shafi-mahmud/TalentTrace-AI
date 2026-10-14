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

def test_real_postgres_booking_races():
 url=os.environ.get('SELF_SCHEDULING_TEST_DATABASE_URL')
 if not url:pytest.skip('Dedicated disposable PostgreSQL required')
 u=make_url(url);assert u.database=='schedule_test' and u.port==54401
 fixtures=[scored(['supported'],weights=ScoringWeights(skill=100,experience=0,education=0)) for _ in range(4)]
 async def run():
  e=create_async_engine(url);f=async_sessionmaker(e,expire_on_commit=False);owner=uuid4();refs=[];raw=[];request=N(client=N(host='synthetic-test'))
  async with f() as s:
   s.add(Recruiter(id=owner,email=f'{owner}@example.test',password_hash='unused',active=True));await s.flush()
   for i in range(4):
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
  await e.dispose()
 asyncio.run(run())
