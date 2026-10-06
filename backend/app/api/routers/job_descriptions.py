from typing import Final

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.schemas.job_description import JobDescriptionGenerationRequest


router = APIRouter(prefix="/job-descriptions", tags=["job descriptions"])

NOT_IMPLEMENTED_RESPONSE: Final[dict[str, str]] = {
    "code": "jd_generation_not_implemented",
    "message": "Job description generation is not implemented yet.",
}


@router.post(
    "/generate",
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
    responses={
        status.HTTP_501_NOT_IMPLEMENTED: {
            "description": "Job description generation is planned but not implemented.",
        }
    },
)
async def generate_job_description(
    _request: JobDescriptionGenerationRequest,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        content=NOT_IMPLEMENTED_RESPONSE,
    )
