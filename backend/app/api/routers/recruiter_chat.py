from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.agents.jd.errors import (
    GenerationProviderError, GenerationTimeoutError, MissingGenerationConfigurationError,
)
from app.integrations.llm.recruiter_chat import get_recruiter_interpreter
from app.rag.retrieval import PolicyRetrievalError
from app.schemas.recruiter_chat import RecruiterChatRequest, RecruiterChatResponse
from app.services.recruiter_chat import RecruiterChatService


router = APIRouter(prefix="/recruiter-chat", tags=["recruiter chat"])


@router.post("", response_model=RecruiterChatResponse, responses={
    502: {"description": "Interpretation or JD generation failed."},
    503: {"description": "Recruiter chat or JD generation is not configured."},
    504: {"description": "Interpretation or JD generation timed out."},
})
async def recruiter_chat(request: RecruiterChatRequest) -> RecruiterChatResponse | JSONResponse:
    try:
        return await RecruiterChatService(get_recruiter_interpreter()).respond(request)
    except MissingGenerationConfigurationError:
        return JSONResponse(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, content={
            "code": "recruiter_chat_not_configured", "message": "Recruiter chat is not configured.",
        })
    except GenerationTimeoutError:
        return JSONResponse(status_code=status.HTTP_504_GATEWAY_TIMEOUT, content={
            "code": "recruiter_chat_timeout", "message": "Recruiter chat timed out. Please try again.",
        })
    except (GenerationProviderError, PolicyRetrievalError):
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "code": "recruiter_chat_failed", "message": "Recruiter chat could not be completed.",
        })
    except Exception:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={
            "code": "recruiter_chat_failed", "message": "Recruiter chat could not be completed.",
        })
