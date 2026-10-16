from fastapi import APIRouter, Depends
from app.core.auth import current_recruiter
from app.api.routers import auth, jobs, interviews, interview_access
from app.api.routers import interview_captions

from app.api.routers import cv_uploads, health, job_descriptions, recruiter_chat, screening


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(interviews.router)
api_router.include_router(interview_access.router)
api_router.include_router(interview_captions.router)
api_router.include_router(job_descriptions.router, dependencies=[Depends(current_recruiter)])
api_router.include_router(recruiter_chat.router, dependencies=[Depends(current_recruiter)])
api_router.include_router(cv_uploads.router, dependencies=[Depends(current_recruiter)])
api_router.include_router(screening.router, dependencies=[Depends(current_recruiter)])

from app.api.routers import self_scheduling
api_router.include_router(self_scheduling.router)

from app.api.routers import interview_email
api_router.include_router(interview_email.router)

from app.api.routers import bulk_scheduling
api_router.include_router(bulk_scheduling.router)

from app.api.routers import transcript_storage
api_router.include_router(transcript_storage.router)

from app.api.routers import interview_analysis
api_router.include_router(interview_analysis.router)
