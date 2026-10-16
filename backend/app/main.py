from typing import Final
from contextlib import asynccontextmanager
import asyncio
from app.services.transcript_runtime import maintenance_loop

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.router import api_router
from app.core.config import settings


PUBLIC_VALIDATION_MESSAGES: Final[dict[str, str]] = {
    "missing": "Field required.",
    "extra_forbidden": "Extra inputs are not permitted.",
    "string_too_short": "Text is shorter than the minimum allowed length.",
    "string_too_long": "Text is longer than the maximum allowed length.",
    "too_short": "List has fewer items than allowed.",
    "too_long": "List has more items than allowed.",
    "enum": "Value is not one of the permitted choices.",
    "greater_than_equal": "Number is below the minimum allowed value.",
    "less_than_equal": "Number is above the maximum allowed value.",
    "int_type": "Value must be an integer.",
    "value_error": "Value failed validation.",
    "json_invalid": "Request body is not valid JSON.",
    "model_attributes_type": "Request body has an invalid structure.",
}


@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(maintenance_loop()) if settings.transcript_storage_enabled else None
    try:
        yield
    finally:
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title=f"{settings.app_name} API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def private_api_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith(settings.api_v1_prefix + "/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def sanitized_request_validation_error_handler(
    _request: Request,
    exception: RequestValidationError,
) -> JSONResponse:
    public_errors = []
    for error in exception.errors():
        error_type = str(error.get("type", "value_error"))
        public_errors.append(
            {
                "loc": error.get("loc", ()),
                "msg": PUBLIC_VALIDATION_MESSAGES.get(
                    error_type,
                    "Invalid request value.",
                ),
                "type": error_type,
            }
        )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        content={"detail": public_errors},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
