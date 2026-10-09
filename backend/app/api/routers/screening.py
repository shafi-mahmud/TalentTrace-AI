"""Bounded synthetic/local batch integration; no arbitrary candidate input."""
from uuid import UUID

from fastapi import APIRouter, Request, Depends, HTTPException
from app.core.auth import current_recruiter, database_session
from app.services.recruiter_records import owned_reference, private_settings
from app.services.candidate_profile import CandidateProfileService
from app.services.score_records import persist_scores
from fastapi.responses import JSONResponse

from app.integrations.llm.candidate_profile import CandidateParserNotConfigured
from app.schemas.batch_screening import BatchScreeningResponse, ReviewedJobSnapshot
from app.schemas.cv_upload import JobReference
from app.services.batch_screening import BatchScreeningService, JobSnapshotMismatch
from app.services.cv_extraction import CvExtractionError, PUBLIC_ERRORS

router = APIRouter(tags=["Candidate screening"])


@router.post("/cv-uploads/{job_reference}/{batch_id}/screen", response_model=BatchScreeningResponse)
async def screen_batch(request: Request, job_reference: JobReference, batch_id: UUID,
                       snapshot: ReviewedJobSnapshot, user=Depends(current_recruiter), session=Depends(database_session)) -> BatchScreeningResponse | JSONResponse:
    job = await authorize_snapshot(session, user.id, snapshot)
    expected_revision = request.headers.get("x-talenttrace-job-revision")
    if job is not None and expected_revision is not None and expected_revision != str(job.revision):
        raise HTTPException(409, "Job changed. Review criteria and weights again.")
    try:
        batch = await BatchScreeningService(profiles=CandidateProfileService(private_settings(request))).screen_batch(job_reference, batch_id, snapshot)
        if job is not None:
            scoring = await persist_scores(session, job, batch)
            return BatchScreeningResponse.model_validate({**batch.model_dump(), "scoring": scoring.model_dump()})
        return batch
    except JobSnapshotMismatch:
        return JSONResponse(status_code=409, content={"code": "screening_job_mismatch",
            "message": "The reviewed job reference must match the uploaded batch."})
    except CandidateParserNotConfigured:
        return JSONResponse(status_code=503, content={"code": "candidate_parser_not_configured",
            "message": "Candidate profile extraction is not configured."})
    except CvExtractionError as error:
        return JSONResponse(status_code=error.status, content={"code": error.code, "message": PUBLIC_ERRORS[error.code]})
    except Exception:
        return JSONResponse(status_code=500, content={"code": "batch_screening_unavailable",
            "message": "Batch screening could not be completed."})


async def authorize_snapshot(session, owner_id, snapshot):
    job = await owned_reference(session, owner_id, snapshot.job_reference, lock=True)
    if job.confirmed_snapshot != snapshot.model_dump(mode="json"):
        raise HTTPException(409, "Review and confirm the current saved requirements before screening.")
    return job
