"""One-shot stdin worker run inside the verified current backend; no Google I/O."""
import asyncio,base64,hashlib,json,sys
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID
from sqlalchemy import select,text
from sqlalchemy.ext.asyncio import async_sessionmaker
from app.core.config import settings
from app.db.session import create_database_engine
from app.db.models.recruiter import Recruiter
from app.services.recruiter_records import owned_job
from app.services.application_bridge import ApplicationImportBridge
from app.schemas.application_bridge import BridgeBinding,ApplicationManifest
from app.schemas.external_cv import respondent_contact

class ImportGateError(Exception):
    pass

async def execute(p):
    binding=BridgeBinding.model_validate(p['binding'])
    if binding.source_job_reference!=binding.target_job_reference or binding.target_job_reference!='TT-JOB-49C51587C3524024':
        raise ImportGateError('target_mismatch')
    if Path(settings.cv_upload_root)!=Path('/app/data/cv_uploads'):raise ImportGateError('storage_mismatch')
    engine=create_database_engine();factory=async_sessionmaker(engine,expire_on_commit=False)
    try:
        async with factory() as db:
            identity=(await db.execute(text('SELECT current_database(),current_user'))).one()
            if tuple(identity)!=('talenttrace_docker_demo','talenttrace_demo'):raise ImportGateError('database_mismatch')
            if (await db.scalar(text('SELECT version_num FROM alembic_version')))!='0017_booked_interview_email':raise ImportGateError('schema_mismatch')
            # Keep this same session/job lock through the existing importer's commit.
            job=await owned_job(db,binding.recruiter_id,binding.target_job_id,lock=True)
            if job.job_reference!=binding.target_job_reference or job.revision!=2:
                raise ImportGateError('job_revision_or_approval_mismatch')
            if not await db.scalar(select(Recruiter.active).where(Recruiter.id==binding.recruiter_id)):raise ImportGateError('inactive_owner')
            if p['action']=='preflight':return {'ready':True,'revision':2,'schema':'0017_booked_interview_email'}
            if p['action']!='import':raise ImportGateError('invalid_action')
            data=base64.b64decode(p['cv_base64'],validate=True)
            if not 0<len(data)<=10*1024*1024 or hashlib.sha256(data).hexdigest()!=p['sha256']:raise ImportGateError('integrity_failed')
            manifest=ApplicationManifest(source_id=binding.source_id,external_submission_id=p['submission_id'],
                source_job_reference=binding.source_job_reference,contact=respondent_contact(p.get('respondent_email')),
                content_type=p['mime'],size_bytes=len(data),sha256=p['sha256'])
            async def reader(b,key):
                if b!=binding or key!=manifest.external_submission_id:raise ImportGateError('source_mismatch')
                return manifest,data
            @asynccontextmanager
            async def shared_session():
                yield db
            bridge=ApplicationImportBridge(shared_session,settings.cv_upload_root,(binding,),reader)
            result=await bridge.import_application(binding.recruiter_id,binding.source_id,manifest.external_submission_id)
            return {'imported':result.created,'reused':not result.created,'status':result.status,'screened':False}
    finally:await engine.dispose()

if __name__=='__main__':
    try:
        raw=sys.stdin.buffer.read(15*1024*1024+1)
        if len(raw)>15*1024*1024:raise ImportGateError('payload_too_large')
        print(json.dumps(asyncio.run(execute(json.loads(raw)))))
    except Exception as e:
        print(json.dumps({'state':'blocked_or_unconfirmed','category':str(e) if isinstance(e,ImportGateError) else getattr(e,'code',type(e).__name__)}));sys.exit(1)
