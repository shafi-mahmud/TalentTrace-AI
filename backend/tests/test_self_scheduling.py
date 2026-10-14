import asyncio
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.services.interview_slots import offered_slots,ZONE
from app.services.interview_booking import check_overlap
from app.api.routers.self_scheduling import Capability,Booking

def test_demo_slots():
 now=datetime(2026,10,15,0,tzinfo=timezone.utc)
 values=offered_slots(now);assert 0<len(values)<=70
 for s in values:
  x=s.astimezone(ZONE);assert s>now and x.weekday()<5
  allowed={(8,0),(9,0),(10,0),(11,0)}|({(14,0),(15,0),(16,0)} if x.weekday()==4 else {(13,30),(14,30),(15,30)})
  assert (x.hour,x.minute) in allowed

def test_overlap_edges():
 start=datetime(2026,10,20,3,tzinfo=timezone.utc)
 class S:
  async def scalars(self,*a):return N(all=lambda:[N(scheduled_at=start,duration_minutes=60)])
 with pytest.raises(HTTPException):asyncio.run(check_overlap(S(),uuid4(),start+timedelta(minutes=30),60))
 asyncio.run(check_overlap(S(),uuid4(),start+timedelta(minutes=60),60))

def test_no_identity_injection():
 from pydantic import ValidationError
 with pytest.raises(ValidationError):Capability(token='A'*43,job_id=str(uuid4()))
 with pytest.raises(ValidationError):Booking(token='A'*43,scheduled_at='2026-10-20T08:00:00')

def test_capability_invalid_expired_booked_stale(monkeypatch):
 from app.api.routers import self_scheduling as m
 from pydantic import ValidationError
 async def run():
  body=Capability(token='A'*43);request=N(client=N(host='offline-invalid-test'))
  class S:
   row=None
   async def scalar(self,*a):return self.row
   async def refresh(self,*a):pass
  async def locked(*a):pass
  async def stale(*a):raise HTTPException(409,'Selection changed')
  monkeypatch.setattr(m,'lock_interviewer',locked);monkeypatch.setattr(m,'selected',stale)
  s=S()
  with pytest.raises(HTTPException) as error:await m.capability(s,body,request)
  assert error.value.status_code==401
  for revoked,expires,booked,expected in [(True,datetime.now(timezone.utc)+timedelta(days=1),None,401),(False,datetime.now(timezone.utc)-timedelta(seconds=1),None,401),(False,datetime.now(timezone.utc)+timedelta(days=1),uuid4(),409),(False,datetime.now(timezone.utc)+timedelta(days=1),None,409)]:
   s.row=N(recruiter_id=uuid4(),job_id=uuid4(),batch_id=uuid4(),upload_id=uuid4(),criteria_revision=2,unscored_confirmed=False,revoked=revoked,expires_at=expires,interview_id=booked)
   with pytest.raises(HTTPException) as error:await m.capability(s,body,request)
   assert error.value.status_code==expected
 asyncio.run(run())

def test_public_routes_require_mutation_header_and_hide_unknown_token():
 from app.main import app
 from app.core.auth import database_session
 from fastapi.testclient import TestClient
 class S:
  async def scalar(self,*a):return None
 async def db():yield S()
 old=dict(app.dependency_overrides);app.dependency_overrides[database_session]=db
 try:
  with TestClient(app) as c:
   assert c.post('/api/v1/interview-scheduling/slots',json={'token':'A'*43}).status_code==403
   r=c.post('/api/v1/interview-scheduling/slots',json={'token':'A'*43},headers={'X-TalentTrace-Request':'1'})
   assert r.status_code==401 and 'A'*43 not in r.text
  assert '/api/v1/interview-scheduling/book' in app.openapi()['paths']
 finally:app.dependency_overrides.clear();app.dependency_overrides.update(old)
