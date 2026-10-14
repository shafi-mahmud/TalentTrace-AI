"""Internal-only F4 import. Trusted handoff is injected by server configuration.

No HTTP/CLI endpoint accepts manifests or provenance claims. The authenticated
backend supplies actor identity; its trusted reader supplies manifest and bytes.
The reader must validate the original source ledger, not client-entered claims.
"""
import hashlib
from io import BytesIO
from starlette.datastructures import UploadFile,Headers
from app.schemas.application_bridge import ApplicationManifest,BridgeBinding
from app.schemas.external_cv import ExternalCvSubmission,ApprovedExternalSource,SubmissionId
from app.services.external_cv import ExternalCvImportService
from pydantic import TypeAdapter

class ApplicationBridgeError(Exception):
    def __init__(self,code):
        self.code=code
        super().__init__('Application handoff rejected ('+code+').')

class ApplicationImportBridge:
    def __init__(self,sessions,storage_root,bindings, trusted_reader):
        bindings=tuple(BridgeBinding.model_validate(b) for b in bindings)
        self.bindings={b.source_id:b for b in bindings}
        if len(self.bindings)!=len(bindings):raise ValueError('Ambiguous source binding')
        self.reader=trusted_reader
        self.importer=ExternalCvImportService(sessions,storage_root,tuple(
            ApprovedExternalSource(source_id=b.source_id,recruiter_id=b.recruiter_id,job_id=b.target_job_id)
            for b in bindings))

    async def import_application(self,actor_id,source_id,submission_id):
        binding=self.bindings.get(source_id)
        if binding is None or binding.recruiter_id!=actor_id:
            raise ApplicationBridgeError('source_not_authorized')
        submission_id=TypeAdapter(SubmissionId).validate_python(submission_id)
        # Ownership is checked BEFORE the trusted reader accesses source documents.
        await self.importer.authorize_source(source_id,binding.target_job_reference)
        manifest,data=await self.reader(binding,submission_id)
        manifest=ApplicationManifest.model_validate(manifest)
        if (manifest.source_id!=source_id or manifest.external_submission_id!=submission_id
            or manifest.source_job_reference!=binding.source_job_reference):
            raise ApplicationBridgeError('source_identity_mismatch')
        if not isinstance(data,bytes) or len(data)!=manifest.size_bytes or hashlib.sha256(data).hexdigest()!=manifest.sha256:
            raise ApplicationBridgeError('file_integrity_failed')
        kind='pdf' if manifest.content_type=='application/pdf' else 'docx'
        upload=UploadFile(BytesIO(data),filename='application.'+kind,headers=Headers({'content-type':manifest.content_type}))
        try:
            return await self.importer.import_submission(ExternalCvSubmission(
                source_id=source_id,external_submission_id=submission_id,
                source_job_reference=binding.source_job_reference,
                job_reference=binding.target_job_reference,application_contact=manifest.contact,
                synthetic=True,cv=upload))
        finally:
            await upload.close()
