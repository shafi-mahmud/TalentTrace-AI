"""Authenticated, owned read-only discovery; screening uses the existing endpoint."""
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from app.core.auth import current_recruiter, database_session
from app.services.recruiter_records import owned_job, private_settings
from app.services.imported_batches import discover
router = APIRouter(tags=['Imported CV batches'])


@router.get('/jobs/{job_id}/imported-batches')
async def imported_batches(request: Request, job_id: UUID, revision: int = Query(ge=1),
        user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id, lock=True)
    if job.revision != revision or job.confirmed_snapshot is None:
        raise HTTPException(409, 'Confirm and reload the current job criteria before reviewing imported batches.')
    return await discover(session, job, private_settings(request).cv_upload_root)
