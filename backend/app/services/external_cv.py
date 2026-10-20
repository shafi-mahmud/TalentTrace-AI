"""Trusted internal import using native storage; no endpoint, network, LLM or screening."""
import hashlib
from datetime import datetime,timezone
import shutil
from pathlib import Path
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool
from app.db.models.recruiter import Recruiter
from app.db.models.external_cv import ExternalCvSubmissionRecord
from app.schemas.external_cv import ApprovedExternalSource, ExternalCvSubmission, ExternalCvImportResult
from app.schemas.cv_upload import CvUploadItem
from app.services.cv_upload import CvUploadService, CvUploadError, CHUNK_BYTES, MAX_FILE_BYTES, document_type
from app.services.cv_extraction import CvExtractionService
from app.services.recruiter_records import owned_job

ERRORS = {
    "submission_deleted": "This source submission was deleted; import is suppressed.",
    "contact_conflict": "Application contact changed; operator review is required.",
    "source_not_approved": "External source is not approved.",
    "job_not_available": "Job is not available for this source.",
    "submission_conflict": "Submission identifier already belongs to different input.",
    "stored_submission_unavailable": "Previously imported file is unavailable; operator review is required.",
    "import_failed": "External CV intake was not confirmed.",
    "confirmation_unknown": "Import confirmation is uncertain; retry the same submission identifier after checking storage.",
}


class ExternalCvImportError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(ERRORS[code])


def fingerprint(upload):
    file_type = document_type(upload)
    digest, size = hashlib.sha256(), 0
    try:
        upload.file.seek(0)
        while block := upload.file.read(CHUNK_BYTES):
            size += len(block)
            if size > MAX_FILE_BYTES:raise CvUploadError("file_too_large", 413)
            digest.update(block)
    finally:upload.file.seek(0)
    if not size:raise CvUploadError("invalid_file_signature")
    return file_type, size, digest.hexdigest()


def remove_new_batch(storage, batch):
    """Only a UUID batch created by this import, never caller-supplied paths."""
    directory = storage.root / batch.job_reference / str(batch.batch_id)
    if (directory.is_symlink() or directory.parent.is_symlink()
        or directory.resolve() != directory or not directory.is_relative_to(storage.root)):
        raise OSError("Unsafe cleanup target")
    shutil.rmtree(directory)


def verify_existing(storage, row, reference):
    files = CvExtractionService(storage.root).batch_files(reference, row.batch_id)
    expected = f"{row.upload_id}.{row.file_type}"
    if len(files) != 1 or files[0].name != expected:raise ValueError("Stored identity unavailable")
    digest = hashlib.sha256()
    with files[0].open("rb") as source:
        while block := source.read(CHUNK_BYTES):digest.update(block)
    if digest.hexdigest() != row.content_sha256:raise ValueError("Stored content unavailable")


def bind_contact(row, contact):
    """Called only inside the owned-job import lock; never guesses candidate identity."""
    if contact is None:
        return False
    values = dict(application_email=contact.email, contact_status=contact.status,
        email_provenance=contact.provenance, email_collection_type=contact.collection_type,
        contact_validation_version=contact.validation_version)
    if row.contact_validation_version is not None:
        if any(getattr(row, key) != value for key, value in values.items()):
            raise ExternalCvImportError("contact_conflict")
        return False
    for key, value in values.items():
        setattr(row, key, value)
    row.contact_updated_at = datetime.now(timezone.utc)
    return True


class ExternalCvImportService:
    def __init__(self, session_factory, storage_root: Path, approved_sources: tuple[ApprovedExternalSource, ...]):
        self.sessions, self.storage_root = session_factory, storage_root
        self.sources = {source.source_id: source for source in approved_sources}
        if len(self.sources) != len(approved_sources):raise ValueError("Duplicate source approval")

    async def authorize_source(self, source_id, reference):
        """Preflight before an adapter reads remote candidate files; import rechecks under lock."""
        source=self.sources.get(source_id)
        if source is None:raise ExternalCvImportError("source_not_approved")
        try:
            async with self.sessions() as session:
                job=await owned_job(session,source.recruiter_id,source.job_id)
                active=await session.scalar(select(Recruiter.active).where(Recruiter.id==source.recruiter_id))
                if not active or job.job_reference!=reference:raise ExternalCvImportError("job_not_available")
        except ExternalCvImportError:raise
        except HTTPException:raise ExternalCvImportError("job_not_available") from None
        except Exception:raise ExternalCvImportError("import_failed") from None

    async def import_submission(self, submission: ExternalCvSubmission):
        source = self.sources.get(submission.source_id)
        if source is None:raise ExternalCvImportError("source_not_approved")
        # Revalidate even if a caller used model_copy/model_construct internally.
        submission = ExternalCvSubmission.model_validate(submission.model_dump() | {"cv": submission.cv})
        storage = CvUploadService(self.storage_root / str(source.recruiter_id))
        batch, commit_started = None, False
        try:
            async with self.sessions() as session:
                try:
                    # One trusted source is explicitly bound to one owned job. The job
                    # lock serializes concurrent imports; DB uniqueness is a second guard.
                    job = await owned_job(session, source.recruiter_id, source.job_id, lock=True)
                    active = await session.scalar(select(Recruiter.active).where(Recruiter.id == source.recruiter_id))
                    if not active or job.job_reference != submission.job_reference:
                        raise ExternalCvImportError("job_not_available")
                    from app.services.submission_deletion import import_suppressed
                    if await import_suppressed(session, source.source_id, submission.external_submission_id):
                        raise ExternalCvImportError('submission_deleted')
                    kind, size, digest = await run_in_threadpool(fingerprint, submission.cv)
                    existing = await session.scalar(select(ExternalCvSubmissionRecord).where(
                        ExternalCvSubmissionRecord.source_id == source.source_id,
                        ExternalCvSubmissionRecord.external_submission_id == submission.external_submission_id))
                    if existing is not None:
                        if (existing.job_id != job.id or existing.source_job_reference != submission.source_job_reference or existing.content_sha256 != digest
                            or existing.file_type != kind or existing.size_bytes != size):
                            raise ExternalCvImportError("submission_conflict")
                        try:await run_in_threadpool(verify_existing, storage, existing, job.job_reference)
                        except Exception:raise ExternalCvImportError("stored_submission_unavailable") from None
                        if bind_contact(existing, submission.application_contact):
                            commit_started = True
                            await session.commit()
                        return self.result(existing, job.job_reference, False)
                    batch = await run_in_threadpool(storage.store_batch, job.job_reference, [submission.cv])
                    file = batch.files[0]
                    row = ExternalCvSubmissionRecord(id=uuid4(), job_id=job.id, source_id=source.source_id,
                        external_submission_id=submission.external_submission_id, source_job_reference=submission.source_job_reference, batch_id=batch.batch_id,
                        upload_id=file.upload_id, file_type=file.file_type, size_bytes=file.size_bytes,
                        content_sha256=digest, status="pending_review")
                    await run_in_threadpool(verify_existing, storage, row, job.job_reference)
                    bind_contact(row, submission.application_contact)
                    session.add(row)
                    await session.flush()
                    commit_started = True
                    await session.commit()
                    return self.result(row, job.job_reference, True)
                except Exception:
                    try:await session.rollback()
                    except Exception:pass
                    raise
        except Exception as error:
            # A failed commit acknowledgement is ambiguous: deleting the file could
            # destroy a successfully committed import. Preserve it for retry/review.
            if commit_started:raise ExternalCvImportError("confirmation_unknown") from None
            if batch is not None:
                try:await run_in_threadpool(remove_new_batch, storage, batch)
                except Exception:raise ExternalCvImportError("import_failed") from None
            if isinstance(error, (ExternalCvImportError, CvUploadError)):raise
            if isinstance(error, HTTPException):raise ExternalCvImportError("job_not_available") from None
            raise ExternalCvImportError("import_failed") from None

    @staticmethod
    def result(row, reference, created):
        return ExternalCvImportResult(submission_id=row.id, job_reference=reference, batch_id=row.batch_id,
            file=CvUploadItem(upload_id=row.upload_id, file_type=row.file_type, size_bytes=row.size_bytes), created=created)
