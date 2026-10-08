"""Bounded synthetic/local batch integration; no arbitrary candidate input."""
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.integrations.llm.candidate_profile import CandidateParserNotConfigured
from app.schemas.batch_screening import BatchScreeningResponse, ReviewedJobSnapshot
from app.schemas.cv_upload import JobReference
from app.services.batch_screening import BatchScreeningService, JobSnapshotMismatch
from app.services.cv_extraction import CvExtractionError, PUBLIC_ERRORS

router = APIRouter(tags=["Candidate screening"])


@router.post("/cv-uploads/{job_reference}/{batch_id}/screen", response_model=BatchScreeningResponse)
async def screen_batch(job_reference: JobReference, batch_id: UUID,
                       snapshot: ReviewedJobSnapshot) -> BatchScreeningResponse | JSONResponse:
    try:
        return await BatchScreeningService().screen_batch(job_reference, batch_id, snapshot)
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
