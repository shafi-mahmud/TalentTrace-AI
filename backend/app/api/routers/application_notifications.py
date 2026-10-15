from uuid import UUID
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from app.core.auth import current_recruiter, database_session
from app.services.recruiter_records import owned_job, private_settings
from app.services.application_notifications import discover, mark_viewed

router = APIRouter(tags=["Application notifications"])


class ApplicationIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: UUID
    upload_id: UUID


class ViewedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applications: list[ApplicationIdentity] = Field(max_length=1000)


@router.get("/jobs/{job_id}/applications")
async def applications(request: Request, job_id: UUID, user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id)
    return await discover(session, job, private_settings(request).cv_upload_root)


@router.post("/jobs/{job_id}/applications/viewed", status_code=204)
async def viewed(request: Request, job_id: UUID, body: ViewedRequest, user=Depends(current_recruiter), session=Depends(database_session)):
    job = await owned_job(session, user.id, job_id)
    await mark_viewed(session, job, private_settings(request).cv_upload_root, body.applications)
