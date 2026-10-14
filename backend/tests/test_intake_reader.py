import asyncio,hashlib
from pathlib import Path
from uuid import uuid4
from types import SimpleNamespace
import pytest
from app.services.intake_reader import IntakeBinding,TrustedIntakeReader
from app.services.application_bridge import ApplicationBridgeError
from test_application_bridge import setup
from test_cv_uploads import PDF

class SourceSession:
 def __init__(self,row,writable=False):self.row=row;self.writable=writable;self.calls=[]
 async def __aenter__(self):return self
 async def __aexit__(self,*args):pass
 async def scalar(self,q):return self.writable
 async def execute(self,q,params=None):
  self.calls.append((str(q),params))
  return SimpleNamespace(mappings=lambda:SimpleNamespace(all=lambda:[] if self.row is None else [self.row]))

def fixture(tmp_path):
 bridge,b,m,target,calls=setup(tmp_path/'target')
 owner,job,batch,upload=uuid4(),uuid4(),uuid4(),uuid4()
 binding=IntakeBinding(target=b,intake_recruiter_id=owner,intake_job_id=job)
 row=dict(source_id=b.source_id,external_submission_id=m['external_submission_id'],job_id=job,batch_id=batch,upload_id=upload,file_type='pdf',size_bytes=len(PDF),content_sha256=hashlib.sha256(PDF).hexdigest(),status='pending_review',application_email='demo@example.test',contact_status='available',email_provenance='google_forms_collected_email',email_collection_type='RESPONDER_INPUT',contact_validation_version=1,job_reference=b.source_job_reference,recruiter_id=owner,active=True)
 root=tmp_path/'source';path=root/str(owner)/b.source_job_reference/str(batch)/(str(upload)+'.pdf');path.parent.mkdir(parents=True);path.write_bytes(PDF)
 session=SourceSession(row);reader=TrustedIntakeReader(lambda:session,root,binding)
 return bridge,b,m,target,reader,session,row,path

def test_actual_storage_reader_wired_import_retry(tmp_path):
 async def run():
  bridge,b,m,target,reader,session,row,path=fixture(tmp_path);bridge.reader=reader
  first=await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  second=await bridge.import_application(b.recruiter_id,b.source_id,m['external_submission_id'])
  assert first.created and not second.created and first.batch_id!=row['batch_id']
  assert target.rows[0].upload_id!=row['upload_id'] and target.rows[0].application_email==row['application_email']
  assert session.calls[0][0]=='SET TRANSACTION READ ONLY'
  params=session.calls[1][1];assert params['job']==row['job_id'] and params['owner']==row['recruiter_id']
  assert path.read_bytes()==PDF
 asyncio.run(run())

@pytest.mark.parametrize('changes',[{'contact_status':None},{'application_email':'invalid'},{'email_provenance':'cv_text'},{'email_collection_type':'VERIFIED'},{'active':False},{'status':'failed'},{'content_sha256':'0'*64},{'size_bytes':1}])
def test_bad_source_data_rejected(tmp_path,changes):
 async def run():
  bridge,b,m,target,reader,session,row,path=fixture(tmp_path);row.update(changes)
  with pytest.raises(ApplicationBridgeError):await reader(b,m['external_submission_id'])
  assert not target.rows
 asyncio.run(run())

@pytest.mark.parametrize('case',['missing','modified','extra','writable','no_row','binding'])
def test_file_permissions_and_lookup_rejection(tmp_path,case):
 async def run():
  bridge,b,m,target,reader,session,row,path=fixture(tmp_path)
  if case=='missing':path.unlink()
  if case=='modified':path.write_bytes(PDF+b'x')
  if case=='extra':(path.parent/'extra.pdf').write_bytes(PDF)
  if case=='writable':session.writable=True
  if case=='no_row':session.row=None
  if case=='binding':b=b.model_copy(update={'target_job_id':uuid4()})
  with pytest.raises(ApplicationBridgeError):await reader(b,m['external_submission_id'])
 asyncio.run(run())
