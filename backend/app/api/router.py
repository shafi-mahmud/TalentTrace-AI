from fastapi import APIRouter

from app.api.routers import health, job_descriptions, recruiter_chat


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(job_descriptions.router)
api_router.include_router(recruiter_chat.router)
