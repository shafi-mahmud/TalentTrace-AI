from typing import Final

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.agents.jd.errors import (
    GenerationProviderError,
    GenerationTimeoutError,
    MissingGenerationConfigurationError,
)
from app.agents.jd.workflow import get_job_description_workflow
from app.rag.retrieval import PolicyRetrievalError
from app.schemas.job_description import (
    JobDescriptionGenerationRequest,
    JobDescriptionGenerationResponse,
)


router = APIRouter(prefix="/job-descriptions", tags=["job descriptions"])

MISSING_CONFIGURATION_RESPONSE: Final[dict[str, str]] = {
    "code": "jd_generation_not_configured",
    "message": "Job description generation is not configured.",
}
TIMEOUT_RESPONSE: Final[dict[str, str]] = {
    "code": "jd_generation_timeout",
    "message": "Job description generation timed out. Please try again.",
}
GENERATION_FAILURE_RESPONSE: Final[dict[str, str]] = {
    "code": "jd_generation_failed",
    "message": "Job description generation could not be completed.",
}


@router.post(
    "/generate",
    status_code=status.HTTP_200_OK,
    response_model=JobDescriptionGenerationResponse,
    responses={
        status.HTTP_502_BAD_GATEWAY: {
            "description": "The generation provider returned an unusable response.",
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "Job-description generation is not configured.",
        },
        status.HTTP_504_GATEWAY_TIMEOUT: {
            "description": "The generation provider timed out.",
        },
    },
)
async def generate_job_description(
    request: JobDescriptionGenerationRequest,
) -> JobDescriptionGenerationResponse | JSONResponse:
    try:
        workflow = get_job_description_workflow()
        return await workflow.generate(request)
    except MissingGenerationConfigurationError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=MISSING_CONFIGURATION_RESPONSE,
        )
    except GenerationTimeoutError:
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=TIMEOUT_RESPONSE,
        )
    except (GenerationProviderError, PolicyRetrievalError):
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=GENERATION_FAILURE_RESPONSE,
        )
