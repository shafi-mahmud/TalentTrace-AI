from fastapi import APIRouter

from app.api.routers import health, job_descriptions


api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(job_descriptions.router)
