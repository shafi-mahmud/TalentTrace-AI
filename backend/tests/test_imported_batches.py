"""Real login/routes/bridge/storage/scoring/PostgreSQL; only external model extraction is doubled."""
import asyncio, hashlib
from uuid import uuid4
import httpx, pytest
from sqlalchemy import select, text, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from pydantic import SecretStr
from app.main import app
from app.core.auth import database_session, hash_password
from app.core.config import settings
from app.db.models.recruiter import Recruiter, CandidateScoreRecord
from app.db.models.external_cv import ExternalCvSubmissionRecord
from app.services.application_bridge import ApplicationImportBridge
from app.schemas.external_cv import respondent_contact
from app.services import candidate_profile
from app.schemas.candidate_profile import CandidateProfileInterpretation
from test_candidate_profile import blank_interpretation
from test_cv_extraction import pdf_bytes
from test_booked_email_postgres import disposable_pg


def test_authenticated_imported_batch_screening_postgres(disposable_pg, tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):raise AssertionError('External network prohibited')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    monkeypatch.setattr(settings, 'cv_upload_root', tmp_path)
    monkeypatch.setattr(settings, 'groq_api_key', SecretStr('unused-synthetic-double'))
    class Extractor:
        calls=0
        fail=False
        entered=None
        release=None
        async def extract(self, document):
            self.calls+=1
            if self.entered:
                self.entered.set();await self.release.wait()
            if self.fail:raise RuntimeError('PRIVATE_PROVIDER_FAILURE')
            value=blank_interpretation();unit=next(u for u in document.units if 'Python' in u.text)
            value['qualifications']['skills']=[{'value':'Python','evidence':'Python','source_id':unit.source_id}]
            return CandidateProfileInterpretation.model_validate(value)
    extractor=Extractor()
    monkeypatch.setattr(candidate_profile,'GroqCandidateProfileExtractor',lambda c:extractor)
    async def run():
        engine=create_async_engine(disposable_pg,echo=False,hide_parameters=True)
        sessions=async_sessionmaker(engine,expire_on_commit=False)
        owner,foreign=uuid4(),uuid4();password='synthetic-import-password-123'
        async def database():
            async with sessions() as db:yield db
        previous=dict(app.dependency_overrides);app.dependency_overrides[database_session]=database
        try:
            async with sessions.begin() as db:
                assert await db.scalar(text('SELECT version_num FROM alembic_version'))=='0017_booked_interview_email'
                for identity,label in [(owner,'owner'),(foreign,'foreign')]:db.add(Recruiter(id=identity,email=label+'-'+identity.hex+'@example.test',password_hash=hash_password(password),active=True))
            def client():return httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers={'Origin':'http://test','X-TalentTrace-Request':'1'})
            async with client() as first,client() as other:
                for c,identity,label in [(first,owner,'owner'),(other,foreign,'foreign')]:
                    assert (await c.post('/api/v1/auth/login',json={'email':label+'-'+identity.hex+'@example.test','password':password})).status_code==200
                async def job(title,approve=True):
                    j=(await first.post('/api/v1/jobs',json={'job_title':title})).json()
                    if approve:
                        j=(await first.put('/api/v1/jobs/'+j['id']+'/criteria',json={'revision':1,'confirmed':True,'weights':{'skill':100,'experience':0,'education':0},'criteria':[{'criterion_id':'python','description':'Python','category':'skill','is_hard':True}]})).json()
                    return j
                a,b,unapproved=await job('Synthetic A'),await job('Synthetic B'),await job('Synthetic unapproved',False)
                data=pdf_bytes()
                async def imported(j,key):
                    binding={'source_id':'synthetic','source_job_reference':j['job_reference'],'recruiter_id':owner,'target_job_id':j['id'],'target_job_reference':j['job_reference']}
                    async def reader(binding,submission):return {'source_id':binding.source_id,'external_submission_id':submission,'source_job_reference':binding.source_job_reference,'contact':respondent_contact('private-synthetic@example.test'),'content_type':'application/pdf','size_bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()},data
                    return await ApplicationImportBridge(sessions,tmp_path,[binding],reader).import_application(owner,'synthetic',key)
                ia,ib,missing,changed,failed=await imported(a,'a'),await imported(b,'b'),await imported(a,'missing'),await imported(a,'changed'),await imported(a,'failed')
                def path(j,i):return tmp_path/str(owner)/j['job_reference']/str(i.batch_id)/(str(i.file.upload_id)+'.pdf')
                path(a,missing).unlink();original=path(a,changed).read_bytes();path(a,changed).write_bytes(original[:20]+bytes([original[20]^1])+original[21:])
                async def discovery(j,c=first):return await c.get('/api/v1/jobs/'+j['id']+'/imported-batches',params={'revision':j['revision']})
                async def screen(j,i,token=None,revision=None,c=first):
                    headers={'X-TalentTrace-Job-Revision':str(revision or j['revision'])}
                    if token:headers['X-TalentTrace-Imported-Review']=token
                    return await c.post('/api/v1/cv-uploads/'+j['job_reference']+'/'+str(i.batch_id)+'/screen',json=j['snapshot'],headers={**headers,"X-TalentTrace-AI-Provider":"groq","X-TalentTrace-External-Processing":"confirmed"})
                assert (await discovery(a,other)).status_code==404
                assert (await discovery(unapproved)).status_code==409
                assert (await first.get('/api/v1/jobs/'+a['id']+'/imported-batches?revision=1')).status_code==409
                response=await discovery(a);assert response.status_code==200
                assert all(secret not in response.text for secret in ['private-synthetic','application_email','content_sha256',str(tmp_path),'source_id'])
                rows={r['batch_id']:r for r in response.json()['batches']};assert len(rows)==4
                assert str(ib.batch_id) not in rows
                assert rows[str(missing.batch_id)]['availability']==rows[str(changed.batch_id)]['availability']=='unavailable'
                assert (await discovery(b)).json()['batches'][0]['batch_id']==str(ib.batch_id)
                assert extractor.calls==0
                token=rows[str(ia.batch_id)]['review_token']
                assert (await screen(a,ia)).status_code==409
                assert (await screen(a,ia,token,revision=1)).status_code==409
                assert (await screen(b,ia,token)).status_code==409
                assert (await screen(a,ia,token,c=other)).status_code==404
                for i in [missing,changed]:assert (await screen(a,i,token)).status_code==409
                # Two actual requests serialize on owned job lock; the stale duplicate cannot call a model.
                extractor.entered=asyncio.Event();extractor.release=asyncio.Event()
                first_task=asyncio.create_task(screen(a,ia,token));entered_task=asyncio.create_task(extractor.entered.wait())
                done,_=await asyncio.wait([first_task,entered_task],timeout=15,return_when=asyncio.FIRST_COMPLETED)
                assert entered_task in done, first_task.result().text if first_task.done() else 'No extraction started'
                await entered_task
                duplicate=asyncio.create_task(screen(a,ia,token));await asyncio.sleep(.1);extractor.release.set()
                good,repeat=await asyncio.gather(first_task,duplicate)
                assert good.status_code==200,good.text
                assert repeat.status_code==409 and extractor.calls==1
                extractor.entered=None
                result=good.json();assert result['scoring']['candidates'][0]['score']==100
                assert result['candidates'][0]['upload_id']==str(ia.file.upload_id)
                saved=await first.get('/api/v1/jobs/'+a['id']+'/batches/'+str(ia.batch_id)+'/scores')
                assert saved.status_code==200 and saved.json()==result['scoring']
                assert (await other.get('/api/v1/jobs/'+a['id']+'/batches/'+str(ia.batch_id)+'/scores')).status_code==404
                assert (await first.get('/api/v1/jobs/'+b['id']+'/batches/'+str(ia.batch_id)+'/scores')).status_code==404
                updated={r['batch_id']:r for r in (await discovery(a)).json()['batches']}
                assert updated[str(ia.batch_id)]['screening_status']=='current_results'
                assert updated[str(ia.batch_id)]['review_token']!=token
                # File replacement after preview is rejected without another model call.
                btoken=(await discovery(b)).json()['batches'][0]['review_token'];path(b,ib).write_bytes(original[:20]+bytes([original[20]^1])+original[21:])
                assert (await screen(b,ib,btoken)).status_code==409 and extractor.calls==1
                extractor.fail=True
                failure=await screen(a,failed,rows[str(failed.batch_id)]['review_token'])
                assert failure.status_code==200 and failure.json()['scoring'] is None
                assert 'PRIVATE_PROVIDER_FAILURE' not in failure.text
                latest={r['batch_id']:r for r in (await discovery(a)).json()['batches']}
                assert latest[str(failed.batch_id)]['screening_status']=='not_screened'
                # A file changed during model work must not replace persisted scores.
                extractor.fail=False;extractor.entered=asyncio.Event();extractor.release=asyncio.Event()
                token2=latest[str(ia.batch_id)]['review_token']
                inflight=asyncio.create_task(screen(a,ia,token2));await asyncio.wait_for(extractor.entered.wait(),15)
                path(a,ia).write_bytes(original[:20]+bytes([original[20]^1])+original[21:]);extractor.release.set()
                assert (await inflight).status_code==409
                extractor.entered=None;path(a,ia).write_bytes(original)
                reloaded=await first.get('/api/v1/jobs/'+a['id']+'/batches/'+str(ia.batch_id)+'/scores')
                assert reloaded.json()==result['scoring']
                # A fresh approved revision invalidates a previously reviewed imported batch.
                stale=latest[str(ia.batch_id)]['review_token']
                updated_job=(await first.put('/api/v1/jobs/'+a['id']+'/criteria',json={'revision':2,'confirmed':True,'weights':{'skill':100,'experience':0,'education':0},'criteria':a['snapshot']['criteria']})).json()
                assert (await screen(a,ia,stale)).status_code==409
                assert (await screen(updated_job,ia,stale)).status_code==409
                older={r['batch_id']:r for r in (await discovery(updated_job)).json()['batches']}
                assert older[str(ia.batch_id)]['screening_status']=='older_revision'
                async with sessions() as db:
                    assert await db.scalar(select(func.count()).select_from(ExternalCvSubmissionRecord))==5
                    assert await db.scalar(select(func.count()).select_from(CandidateScoreRecord))==2
        finally:
            app.dependency_overrides.clear();app.dependency_overrides.update(previous);await engine.dispose()
    asyncio.run(run())
