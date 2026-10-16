"""Recruiter-only F6 reads; no candidate capability or inference endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from app.core.auth import current_recruiter, database_session
from app.core.config import settings
from app.schemas.consolidated_assessment import ConsolidatedAssessment
from app.services.consolidated_assessment import consolidated_assessment

router = APIRouter(tags=['Consolidated candidate assessment'])


@router.get('/jobs/{job_id}/batches/{batch_id}/candidates/{upload_id}/assessment', response_model=ConsolidatedAssessment)
async def report(job_id: UUID, batch_id: UUID, upload_id: UUID, request: Request,
                 user=Depends(current_recruiter), session=Depends(database_session)):
    try:
        return await consolidated_assessment(session, request, user, job_id, batch_id, upload_id,
            storage_enabled=settings.transcript_storage_enabled)
    except SQLAlchemyError:
        raise HTTPException(503, 'Saved candidate assessment is unavailable.') from None
