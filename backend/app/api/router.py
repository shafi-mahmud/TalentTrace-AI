from fastapi import APIRouter, Depends
from app.core.auth import current_recruiter
from app.api.routers import auth, jobs

from app.api.routers import cv_uploads, health, job_descriptions, recruiter_chat, screening


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(jobs.router)
api_router.include_router(job_descriptions.router, dependencies=[Depends(current_recruiter)])
api_router.include_router(recruiter_chat.router, dependencies=[Depends(current_recruiter)])
api_router.include_router(cv_uploads.router, dependencies=[Depends(current_recruiter)])
api_router.include_router(screening.router, dependencies=[Depends(current_recruiter)])
