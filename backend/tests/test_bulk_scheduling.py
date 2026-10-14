import asyncio,json,os,subprocess
from types import SimpleNamespace as N
from uuid import uuid4
import pytest
from fastapi import HTTPException
from app.services.bulk_scheduling import calculate,digest,preview,send,status_reply
from app.schemas.candidate_score import ScoringWeights
from app.services.score_records import SCORING_VERSION
from test_candidate_scoring import scored
from test_interview_email import config

def fixtures(addresses=('approved@synthetic.invalid',)):
 c=config();c.interview_email_recipients=list(addresses)
 scores=[];contacts=[];owner,job_id=uuid4(),uuid4()
 for address in addresses:
  score,_,criteria=scored(['supported'],weights=ScoringWeights(skill=100,experience=0,education=0))
  row=N(id=uuid4(),job_id=job_id,batch_id=uuid4(),upload_id=score.upload_id,criteria_revision=2,scoring_version=SCORING_VERSION,score=score.score,payload=score.model_dump(mode='json'))
  scores.append(row);contacts.append(N(id=uuid4(),job_id=job_id,batch_id=row.batch_id,upload_id=row.upload_id,source_id='synthetic_google',external_submission_id='synthetic_'+row.batch_id.hex,application_email=address,contact_status='available',email_provenance='google_forms_collected_email',email_collection_type='RESPONDER_INPUT',contact_validation_version=1,status='pending_review',content_sha256='a'*64,source_job_reference='TT-JOB-AAAAAAAAAAAAAAAA'))
 job=N(id=job_id,recruiter_id=owner,job_reference=score.job_reference,revision=2,confirmed_snapshot={'job_reference':score.job_reference,'job_title':'Synthetic bulk','criteria_confirmed':True,'criteria':[r.model_dump(mode='json') for r in criteria]},scoring_weights=score.weights.model_dump())
 return job,scores,contacts,c

def test_valid_original_contact_and_no_private_email_in_preview():
 j,s,a,c=fixtures();data,targets,_=calculate(j,s,a,set(),set(),c)
 assert data['sendable']==1 and data['can_send'] and list(targets.values())==[a[0].application_email]
 assert a[0].application_email not in json.dumps(data)

@pytest.mark.parametrize('case,reason',[('stale','stale_criteria'),('version','stale_criteria'),('unscored','not_scored'),('excluded','ineligible'),('missing','missing_or_ambiguous_contact'),('ambiguous','missing_or_ambiguous_contact'),('malformed','missing_or_ambiguous_contact'),('foreign_contact','missing_or_ambiguous_contact'),('unapproved','not_allowlisted'),('booked','already_scheduled'),('invited','already_invited')])
def test_exclusions(case,reason):
 j,s,a,c=fixtures();booked=set();invited=set();pair=(s[0].batch_id,s[0].upload_id)
 if case=='stale':s[0].criteria_revision=1
 if case=='version':s[0].scoring_version='old'
 if case in ('unscored','excluded'):
  score,_,_=scored(['ambiguous' if case=='unscored' else 'not_found'],hard=case=='excluded',weights=ScoringWeights(skill=100,experience=0,education=0));s[0].payload=score.model_dump(mode='json');s[0].score=score.score
 if case=='missing':a=[]
 if case=='ambiguous':a.append(a[0])
 if case=='malformed':a[0].application_email='invalid'
 if case=='foreign_contact':a[0].job_id=uuid4()
 if case=='unapproved':c.interview_email_recipients=[]
 if case=='booked':booked.add(pair)
 if case=='invited':invited.add(pair)
 data,targets,_=calculate(j,s,a,booked,invited,c)
 assert data['sendable']==0 and data['exclusions'].get(reason)==1 and not targets

def test_duplicates_exclude_both_without_arbitrary_choice():
 j,s,a,c=fixtures(('approved@synthetic.invalid','approved@synthetic.invalid'))
 data,targets,_=calculate(j,s,a,set(),set(),c)
 assert data['exclusions']=={'duplicate_recipient':2} and not targets

def test_email_and_score_change_fingerprint():
 j,s,a,c=fixtures();_,_,before=calculate(j,s,a,set(),set(),c)
 a[0].external_submission_id='different'
 assert calculate(j,s,a,set(),set(),c)[2]!=before

def test_confirmation_is_strict():
 from app.api.routers.bulk_scheduling import Approval
 from pydantic import ValidationError
 for value in [False,1,'true']:
  with pytest.raises(ValidationError):Approval(operation_id=uuid4(),confirmed=value)

@pytest.mark.parametrize("smtp_outcome",["accepted","failed","uncertain"])
def test_real_postgres_bulk_concurrency_stale_partial_and_token_isolation(monkeypatch,smtp_outcome):
 if os.environ.get('BULK_SCHEDULING_PG_TEST')!='1':pytest.skip('Explicit disposable PostgreSQL only')
 from io import StringIO
 from alembic import command
 from alembic.config import Config
 from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
 from sqlalchemy.engine import URL
 from sqlalchemy import select,func
 from app.db.models.recruiter import Recruiter,JobProfile,CandidateScoreRecord,SchedulingInvitation,InterviewEmailAttempt
 from app.db.models.external_cv import ExternalCvSubmissionRecord
 from app.db.models.bulk_scheduling import BulkSchedulingOperation
 from app.services import interview_email as transport
 container='talenttrace-self-schedule-test-20261014';database='bulk_scheduling_test_'+uuid4().hex[:10]
 subprocess.run(['docker','exec',container,'createdb','-U','schedule_test',database],capture_output=True,check=True)
 output=StringIO();command.upgrade(Config('alembic.ini',output_buffer=output),'head',sql=True)
 result=subprocess.run(['docker','exec','-i',container,'psql','-v','ON_ERROR_STOP=1','-U','schedule_test','-d',database],input=output.getvalue(),text=True,capture_output=True)
 assert result.returncode==0,'Disposable migration failed'
 info=json.loads(subprocess.run(['docker','inspect',container],capture_output=True,text=True,check=True).stdout)[0]
 password=next(v.split('=',1)[1] for v in info['Config']['Env'] if v.startswith('POSTGRES_PASSWORD='))
 url=URL.create('postgresql+asyncpg',username='schedule_test',password=password,host='127.0.0.1',port=54401,database=database)
 class SMTP:
  def __init__(self):self.calls=[]
  def send(self,*args):
   self.calls.append(args)
   if len(self.calls)==2 and smtp_outcome=='uncertain':raise TimeoutError('PRIVATE SMTP detail')
   if len(self.calls)==2 and smtp_outcome=='failed':
    import smtplib
    raise smtplib.SMTPAuthenticationError(535,b'PRIVATE SMTP detail')
 smtp=SMTP();monkeypatch.setattr(transport,'SMTPTransport',lambda:smtp)
 j,s,a,c=fixtures(('approved@synthetic.invalid','other@synthetic.invalid'))
 async def run():
  engine=create_async_engine(url,hide_parameters=True);factory=async_sessionmaker(engine,expire_on_commit=False)
  try:
   async with factory() as session:
    session.add(Recruiter(id=j.recruiter_id,email='owner@example.test',password_hash='synthetic',active=True));await session.flush()
    session.add(JobProfile(id=j.id,recruiter_id=j.recruiter_id,job_reference=j.job_reference,job_title='Synthetic bulk',suggestions={},sources=[],revision=2,confirmed_snapshot=j.confirmed_snapshot,scoring_weights=j.scoring_weights));await session.flush()
    for row,contact in zip(s,a):
     session.add(CandidateScoreRecord(**vars(row)))
     session.add(ExternalCvSubmissionRecord(**vars(contact),file_type='pdf',size_bytes=100))
    await session.commit()
   async with factory() as session:
    with pytest.raises(HTTPException) as e:await preview(session,uuid4(),j.id,'2',c)
    assert e.value.status_code==404
   async with factory() as session:stale=await preview(session,j.recruiter_id,j.id,'2',c)
   async with factory() as session:
    contact=await session.get(ExternalCvSubmissionRecord,a[0].id);contact.external_submission_id+='changed';await session.commit()
   async with factory() as session:
    with pytest.raises(HTTPException) as e:await send(session,j.recruiter_id,j.id,stale['operation_id'],'2',c)
    assert e.value.status_code==409 and not smtp.calls
   async with factory() as session:fresh=await preview(session,j.recruiter_id,j.id,'2',c)
   from uuid import UUID
   operation_id=UUID(fresh['operation_id'])
   async def execute():
    async with factory() as session:return await send(session,j.recruiter_id,j.id,operation_id,'2',c)
   results=await asyncio.gather(execute(),execute())
   assert len(smtp.calls)==2
   terminal='completed' if smtp_outcome=='accepted' else 'partial'
   assert any(r['status']==terminal and r['counts'][smtp_outcome]==(2 if smtp_outcome=='accepted' else 1) for r in results)
   tokens=[args[-1].split('#schedule=',1)[1].split()[0] for args in smtp.calls]
   assert tokens[0]!=tokens[1]
   async with factory() as session:
    repeated=await send(session,j.recruiter_id,j.id,operation_id,'2',c)
    assert repeated['status']==terminal and len(smtp.calls)==2
    after=await preview(session,j.recruiter_id,j.id,'2',c);assert after['preview']['sendable']==0
    assert await session.scalar(select(func.count()).select_from(SchedulingInvitation))==2
    assert await session.scalar(select(func.count()).select_from(InterviewEmailAttempt))==2
    from app.core.auth import token_hash
    capabilities=(await session.scalars(select(SchedulingInvitation))).all()
    for args,raw in zip(smtp.calls,tokens):
     cap=next(x for x in capabilities if x.recipient_email==args[1])
     contact=next(x for x in a if x.application_email==args[1])
     assert cap.token_hash==token_hash(raw) and cap.batch_id==contact.batch_id and cap.upload_id==contact.upload_id
    assert await session.scalar(select(func.count()).select_from(ExternalCvSubmissionRecord))==2
    op=await session.get(BulkSchedulingOperation,operation_id)
    saved=await status_reply(session,op);assert saved['counts'][smtp_outcome]==(2 if smtp_outcome=='accepted' else 1)
    assert all(token not in json.dumps(saved,default=str) for token in tokens)
    # Simulate interrupted outcome persistence; GET recovers from exact attempt IDs.
    from datetime import datetime,timedelta,timezone
    op.status='running';op.updated_at=datetime.now(timezone.utc)-timedelta(minutes=6)
    op.outcomes=[{**x,'status':'pending'} for x in op.outcomes];await session.commit()
    recovered=await status_reply(session,op)
    assert recovered['status']=='review_required' and recovered['counts'][smtp_outcome]==(2 if smtp_outcome=='accepted' else 1)
    assert all('attempt_id' not in row for row in recovered['outcomes']) and len(smtp.calls)==2
  finally:await engine.dispose()
 asyncio.run(run())

def test_duplicate_with_booked_application_does_not_select_other_arbitrarily():
 j,s,a,c=fixtures(('approved@synthetic.invalid','approved@synthetic.invalid'))
 data,targets,_=calculate(j,s,a,{(s[0].batch_id,s[0].upload_id)},set(),c)
 assert not targets and data['exclusions']=={'already_scheduled':1,'duplicate_recipient':1}

def test_source_job_change_invalidates_preview():
 j,s,a,c=fixtures();before=calculate(j,s,a,set(),set(),c)[2]
 a[0].source_job_reference='TT-JOB-BBBBBBBBBBBBBBBB'
 assert calculate(j,s,a,set(),set(),c)[2]!=before

def test_bulk_routes_protected_and_schema_rejects_recipient_list(monkeypatch):
 import httpx
 from app.main import app
 from app.core.auth import current_recruiter,database_session
 original=dict(app.dependency_overrides)
 async def denied():raise HTTPException(401,'Sign in required')
 async def database():yield N()
 app.dependency_overrides[current_recruiter]=denied;app.dependency_overrides[database_session]=database
 async def run():
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
   response=await client.post('/api/v1/jobs/'+str(uuid4())+'/bulk-scheduling/preview',json={})
   assert response.status_code==401
 try:asyncio.run(run())
 finally:app.dependency_overrides.clear();app.dependency_overrides.update(original)
 from app.api.routers.bulk_scheduling import Approval
 from pydantic import ValidationError
 with pytest.raises(ValidationError):Approval(operation_id=uuid4(),confirmed=True,recipients=['private@synthetic.invalid'])
