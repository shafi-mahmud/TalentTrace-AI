"""Recruiter-only F6 reads; no candidate capability or inference endpoints."""
from uuid import UUID
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from app.core.auth import current_recruiter, database_session
from app.core.config import settings
from app.schemas.consolidated_assessment import ConsolidatedAssessment, CandidateComparison, ApplicationDiscovery
from app.services.consolidated_assessment import consolidated_assessment

router = APIRouter(tags=['Consolidated candidate assessment'])


async def snapshot_session(session=Depends(database_session)):
    # Must resolve BEFORE current_recruiter: isolation cannot change after its SELECT.
    # Auth's database_session dependency reuses this same request-cached session.
    await session.connection(execution_options={'isolation_level': 'REPEATABLE READ'})
    return session


@router.get('/jobs/{job_id}/batches/{batch_id}/candidates/{upload_id}/assessment', response_model=ConsolidatedAssessment)
async def report(job_id: UUID, batch_id: UUID, upload_id: UUID, request: Request,
                 user=Depends(current_recruiter), session=Depends(database_session)):
    try:
        return await consolidated_assessment(session, request, user, job_id, batch_id, upload_id,
            storage_enabled=settings.transcript_storage_enabled)
    except SQLAlchemyError:
        raise HTTPException(503, 'Saved candidate assessment is unavailable.') from None


@router.get('/jobs/{job_id}/assessment-comparison', response_model=CandidateComparison)
async def comparison(job_id: UUID, left_batch: UUID, left_upload: UUID, right_batch: UUID, right_upload: UUID,
                     request: Request, session=Depends(snapshot_session), user=Depends(current_recruiter)):
    from app.services.consolidated_assessment import compare_assessments
    try:
        return await compare_assessments(session, request, user, job_id,
            ((left_batch, left_upload), (right_batch, right_upload)),
            storage_enabled=settings.transcript_storage_enabled)
    except SQLAlchemyError:
        raise HTTPException(503, 'Candidate comparison is unavailable.') from None


@router.get('/jobs/{job_id}/assessment-applications', response_model=ApplicationDiscovery)
async def applications(job_id: UUID, request: Request, session=Depends(snapshot_session), user=Depends(current_recruiter)):
    from app.services.assessment_discovery import discover_applications
    try:
        return await discover_applications(session, user, job_id)
    except SQLAlchemyError:
        raise HTTPException(503, 'Application discovery is unavailable.') from None
