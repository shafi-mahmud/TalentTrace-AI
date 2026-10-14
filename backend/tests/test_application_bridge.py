"""Trusted internal handoff, synthetic data only; no provider or SMTP calls."""
import asyncio,hashlib
from uuid import uuid4
from types import SimpleNamespace
import pytest
from pydantic import ValidationError
from app.schemas.application_bridge import BridgeBinding,ApplicationManifest
from app.schemas.external_cv import respondent_contact
from app.services.application_bridge import ApplicationImportBridge,ApplicationBridgeError
from app.services.external_cv import ExternalCvImportError
from app.services.cv_extraction import CvExtractionService
from test_external_cv_intake import Session,REFERENCE
from test_cv_uploads import PDF

def setup(tmp_path,**changes):
 b=BridgeBinding(source_id='synthetic_google',source_job_reference='TT-JOB-AAAAAAAAAAAAAAAA',recruiter_id=uuid4(),target_job_id=uuid4(),target_job_reference=REFERENCE)
 source=SimpleNamespace(job_id=b.target_job_id,recruiter_id=b.recruiter_id)
 session=Session(source);calls=[]
 m=dict(source_id=b.source_id,external_submission_id='gform_synthetic_001',source_job_reference=b.source_job_reference,contact=respondent_contact('demo@example.test'),content_type='application/pdf',size_bytes=len(PDF),sha256=hashlib.sha256(PDF).hexdigest())
 m.update(changes)
 async def reader(binding,key):calls.append(key);return m,PDF
 bridge=ApplicationImportBridge(lambda:session,tmp_path,(b,),reader)
 return bridge,b,m,session,calls

def test_import_retry_native_storage_and_contact(tmp_path):
 async def run():
  bridge,b,m,s,calls=setup(tmp_path)
  a=await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  again=await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  assert a.created and not again.created and a.batch_id==again.batch_id and len(s.rows)==1
  r=s.rows[0];assert r.job_id==b.target_job_id and r.source_job_reference==b.source_job_reference and r.application_email=='demo@example.test'
  files=CvExtractionService(tmp_path/str(b.recruiter_id)).batch_files(REFERENCE,a.batch_id)
  assert len(files)==1 and files[0].name==str(a.file.upload_id)+'.pdf'
  assert a.batch_id!=b.target_job_id
 asyncio.run(run())

@pytest.mark.parametrize('change',[{'source_id':'other'},{'source_job_reference':'TT-JOB-BBBBBBBBBBBBBBBB'},{'external_submission_id':'different'},{'sha256':'0'*64},{'size_bytes':1}])
def test_manifest_identity_integrity_rejected(tmp_path,change):
 async def run():
  bridge,b,m,s,calls=setup(tmp_path,**change)
  with pytest.raises(ApplicationBridgeError):await bridge.import_application(b.recruiter_id,b.source_id,'gform_synthetic_001')
  assert not s.rows and not list(tmp_path.rglob('*.pdf'))
 asyncio.run(run())

def test_wrong_recruiter_does_not_access_reader(tmp_path):
 async def run():
  bridge,b,m,s,calls=setup(tmp_path)
  with pytest.raises(ApplicationBridgeError):await bridge.import_application(uuid4(),b.source_id,m['external_submission_id'])
  assert not calls
 asyncio.run(run())

def test_untrusted_provenance_rejected():
 with pytest.raises(ValidationError):ApplicationManifest(source_id='synthetic_google',external_submission_id='x',source_job_reference=REFERENCE,contact={'status':'available','email':'demo@example.test','provenance':'cv_text'},content_type='application/pdf',size_bytes=1,sha256='a'*64)

def test_conflicting_contact_retry_preserves_original(tmp_path):
 async def run():
  bridge,b,m,s,calls=setup(tmp_path)
  await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  m['contact']=respondent_contact('changed@example.test')
  with pytest.raises(ExternalCvImportError) as e:await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  assert e.value.code=='contact_conflict' and s.rows[0].application_email=='demo@example.test' and len(s.rows)==1
 asyncio.run(run())

def test_missing_contact_import_remains_unavailable(tmp_path):
 async def run():
  bridge,b,m,s,calls=setup(tmp_path,contact=respondent_contact(None))
  await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  assert s.rows[0].contact_status=='missing' and s.rows[0].application_email is None
 asyncio.run(run())

def test_native_screening_uses_new_upload_identity(tmp_path):
 async def run():
  from app.schemas.batch_screening import ReviewedJobSnapshot
  from app.services.batch_screening import BatchScreeningService
  from app.agents.screening.workflow import CandidateScreeningWorkflow
  from test_batch_screening import candidate,Profiles,snapshot
  from test_screening_matching import FakeMatcher
  bridge,b,m,s,calls=setup(tmp_path)
  imported=await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  profile=candidate().model_copy(update={'upload_id':imported.file.upload_id})
  profiles=Profiles([profile]);matcher=FakeMatcher(error=AssertionError('No provider call expected'))
  reviewed=ReviewedJobSnapshot.model_validate(snapshot(job_reference=REFERENCE))
  result=await BatchScreeningService(profiles,CandidateScreeningWorkflow(matcher)).screen_batch(REFERENCE,imported.batch_id,reviewed)
  assert result.candidates[0].upload_id==imported.file.upload_id
  assert result.candidates[0].result.screening_decision=='eligible'
  assert profiles.calls==[(REFERENCE,imported.batch_id)]
 asyncio.run(run())

def test_real_postgres_concurrent_import_and_migration(tmp_path):
 import os,subprocess,json
 if os.environ.get('F4_BRIDGE_PG_TEST')!='1':pytest.skip('Explicit disposable PostgreSQL test only')
 from alembic import command
 from alembic.config import Config
 from io import StringIO
 from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
 from sqlalchemy.engine import URL
 from sqlalchemy import select,func
 from app.db.models.recruiter import Recruiter,JobProfile
 from app.db.models.external_cv import ExternalCvSubmissionRecord
 container='talenttrace-self-schedule-test-20261014'
 database='f4_application_bridge_test_'+uuid4().hex[:10]
 subprocess.run(['docker','exec',container,'createdb','-U','schedule_test',database],check=True,capture_output=True)
 output=StringIO();command.upgrade(Config('alembic.ini',output_buffer=output),'head',sql=True)
 migration=subprocess.run(['docker','exec','-i',container,'psql','-v','ON_ERROR_STOP=1','-U','schedule_test','-d',database],input=output.getvalue(),text=True,capture_output=True)
 assert migration.returncode==0,'Disposable migration failed'
 info=json.loads(subprocess.run(['docker','inspect',container],capture_output=True,text=True,check=True).stdout)[0]
 password=next(v.split('=',1)[1] for v in info['Config']['Env'] if v.startswith('POSTGRES_PASSWORD='))
 url=URL.create('postgresql+asyncpg',username='schedule_test',password=password,host='127.0.0.1',port=54401,database=database)
 async def run():
  engine=create_async_engine(url,hide_parameters=True);factory=async_sessionmaker(engine,expire_on_commit=False)
  owner,job=uuid4(),uuid4()
  try:
   async with factory() as session:
    session.add(Recruiter(id=owner,email=owner.hex+'@example.test',password_hash='synthetic',active=True));await session.flush()
    session.add(JobProfile(id=job,recruiter_id=owner,job_reference=REFERENCE,job_title='Synthetic bridge',suggestions={},sources=[],revision=2));await session.commit()
   b=BridgeBinding(source_id='synthetic_google',source_job_reference='TT-JOB-AAAAAAAAAAAAAAAA',recruiter_id=owner,target_job_id=job,target_job_reference=REFERENCE)
   async def reader(binding,key):return dict(source_id=b.source_id,external_submission_id=key,source_job_reference=b.source_job_reference,contact=respondent_contact('demo@example.test'),content_type='application/pdf',size_bytes=len(PDF),sha256=hashlib.sha256(PDF).hexdigest()),PDF
   bridge=ApplicationImportBridge(factory,tmp_path,(b,),reader)
   results=await asyncio.gather(*(bridge.import_application(owner,b.source_id,'same_submission') for _ in range(3)))
   assert sum(r.created for r in results)==1 and len({r.batch_id for r in results})==1
   async with factory() as session:
    rows=(await session.scalars(select(ExternalCvSubmissionRecord))).all()
    assert len(rows)==1 and rows[0].job_id==job and rows[0].application_email=='demo@example.test'
   assert len(list(tmp_path.rglob('*.pdf')))==1
  finally:await engine.dispose()
 asyncio.run(run())
