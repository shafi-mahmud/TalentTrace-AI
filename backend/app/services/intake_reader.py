"""Bounded local read-only ledger handoff. No scores, network APIs or writes."""
import asyncio
import hashlib
from itertools import islice
from pathlib import Path
from uuid import UUID
from pydantic import BaseModel,ConfigDict
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile,Headers
from io import BytesIO
from app.schemas.application_bridge import BridgeBinding,ApplicationManifest
from app.schemas.external_cv import ApplicationContact,SubmissionId
from app.services.application_bridge import ApplicationBridgeError
from app.services.cv_upload import document_type,MAX_FILE_BYTES
from pydantic import TypeAdapter

class IntakeBinding(BaseModel):
    model_config=ConfigDict(extra='forbid',frozen=True)
    target:BridgeBinding
    intake_recruiter_id:UUID
    intake_job_id:UUID

LOOKUP=text("""SELECT e.source_id,e.external_submission_id,e.job_id,e.batch_id,e.upload_id,
 e.file_type,e.size_bytes,e.content_sha256,e.status,e.application_email,e.contact_status,
 e.email_provenance,e.email_collection_type,e.contact_validation_version,
 j.job_reference,j.recruiter_id,r.active
 FROM external_cv_submissions e JOIN job_profiles j ON j.id=e.job_id
 JOIN recruiters r ON r.id=j.recruiter_id
 WHERE e.source_id=:source AND e.external_submission_id=:submission
 AND e.job_id=:job AND j.recruiter_id=:owner AND j.job_reference=:reference""")
PRIVILEGES=text("""SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=current_user AND (rolsuper OR rolcreaterole))
 OR has_table_privilege(current_user,'external_cv_submissions','INSERT,UPDATE,DELETE,TRUNCATE')
 OR has_table_privilege(current_user,'job_profiles','INSERT,UPDATE,DELETE,TRUNCATE')
 OR has_table_privilege(current_user,'recruiters','INSERT,UPDATE,DELETE,TRUNCATE') AS writable""")

def read_cv(root,row):
    root=Path(root)
    if not root.is_absolute():raise ApplicationBridgeError('source_storage_unsafe')
    if row['file_type'] not in ('pdf','docx'):raise ApplicationBridgeError('source_file_type_invalid')
    path=root/str(row['recruiter_id'])/row['job_reference']/str(row['batch_id'])/(str(row['upload_id'])+'.'+row['file_type'])
    for part in (path,*path.parents):
        if part.is_symlink() or part.is_junction():raise ApplicationBridgeError('source_storage_unsafe')
    if not path.is_file() or path.resolve()!=path.absolute() or not path.is_relative_to(root):
        raise ApplicationBridgeError('source_file_unavailable')
    if len(list(islice(path.parent.iterdir(),2)))!=1:raise ApplicationBridgeError('source_storage_ambiguous')
    size=row['size_bytes']
    if type(size)!=int or not 0<size<=MAX_FILE_BYTES or path.stat().st_size!=size:
        raise ApplicationBridgeError('source_file_integrity_failed')
    with path.open('rb') as stream:data=stream.read(MAX_FILE_BYTES+1)
    if len(data)!=size or hashlib.sha256(data).hexdigest()!=row['content_sha256']:
        raise ApplicationBridgeError('source_file_integrity_failed')
    mime={'pdf':'application/pdf','docx':'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}.get(row['file_type'])
    if mime is None:raise ApplicationBridgeError('source_file_type_invalid')
    upload=UploadFile(BytesIO(data),filename='application.'+row['file_type'],headers=Headers({'content-type':mime}))
    try:
        if document_type(upload)!=row['file_type']:raise ApplicationBridgeError('source_file_type_invalid')
    finally:upload.file.close()
    return data,mime

class TrustedIntakeReader:
    def __init__(self,sessions,storage_root,binding):
        self.sessions=sessions;self.root=Path(storage_root);self.binding=IntakeBinding.model_validate(binding)

    async def __call__(self,target,submission_id):
        try:
            async with asyncio.timeout(10):
                return await self._read(target,submission_id)
        except TimeoutError:raise ApplicationBridgeError("source_read_timeout") from None

    async def _read(self,target,submission_id):
        if target!=self.binding.target:raise ApplicationBridgeError('source_binding_mismatch')
        submission_id=TypeAdapter(SubmissionId).validate_python(submission_id)
        try:
            async with self.sessions() as session:
                await session.execute(text('SET TRANSACTION READ ONLY'))
                if await session.scalar(PRIVILEGES):raise ApplicationBridgeError('source_role_not_readonly')
                result=await session.execute(LOOKUP,dict(source=target.source_id,submission=submission_id,
                    job=self.binding.intake_job_id,owner=self.binding.intake_recruiter_id,reference=target.source_job_reference))
                rows=result.mappings().all()
                if len(rows)!=1:raise ApplicationBridgeError('source_submission_unavailable')
                row=dict(rows[0])
                if not row['active'] or row['status']!='pending_review':raise ApplicationBridgeError('source_submission_unavailable')
                if row['contact_status']!='available' or row['contact_validation_version']!=1:
                    raise ApplicationBridgeError('source_contact_unavailable')
                contact=ApplicationContact(email=row['application_email'],status=row['contact_status'],
                    provenance=row['email_provenance'],collection_type=row['email_collection_type'],validation_version=row['contact_validation_version'])
                data,mime=await run_in_threadpool(read_cv,self.root,row)
                manifest=ApplicationManifest(source_id=row['source_id'],external_submission_id=row['external_submission_id'],
                    source_job_reference=row['job_reference'],contact=contact,content_type=mime,size_bytes=len(data),sha256=row['content_sha256'])
                return manifest,data
        except ApplicationBridgeError:raise
        except Exception:raise ApplicationBridgeError('source_read_failed') from None
