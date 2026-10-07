"""Trusted local-demo multipart intake, with bounded parser input and safe errors."""
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException
from starlette.formparsers import MultiPartException

from app.core.config import settings
from app.schemas.cv_upload import CvUploadResponse
from app.services.cv_upload import CvUploadError, CvUploadService, PUBLIC_ERRORS

# Includes 1 MiB for multipart headers/boundaries; document bytes have a separate limit.
MAX_REQUEST_BYTES = 101 * 1024 * 1024
router = APIRouter(tags=["CV intake"])


@router.post("/cv-uploads", response_model=CvUploadResponse, status_code=201,
    responses={400: {"description": "Invalid multipart batch or document."},
        413: {"description": "File, batch or request exceeds limits."},
        415: {"description": "Unsupported request or document type."},
        422: {"description": "Invalid demo Job Reference."},
        500: {"description": "Storage failed; no upload confirmed."}},
    openapi_extra={"requestBody": {"required": True, "content": {"multipart/form-data": {
        "schema": {"type": "object", "additionalProperties": False,
            "required": ["job_reference", "files"], "properties": {
                "job_reference": {"type": "string", "pattern": "^TT-JOB-[A-F0-9]{16}$", "maxLength": 23},
                "files": {"type": "array", "minItems": 1, "maxItems": 20,
                    "items": {"type": "string", "format": "binary"}},
            }}}}}})
async def upload_cvs(request: Request) -> CvUploadResponse | JSONResponse:
    received = 0
    exceeded = False

    async def bounded_receive():
        nonlocal received, exceeded
        message = await request.receive()
        received += len(message.get("body", b""))
        if received > MAX_REQUEST_BYTES:
            exceeded = True
            raise MultiPartException("Upload request exceeds size limit.")
        return message

    try:
        if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "multipart/form-data":
            raise CvUploadError("invalid_multipart", 415)
        length = request.headers.get("content-length")
        if length is not None:
            if not length.isdecimal():
                raise CvUploadError("invalid_multipart")
            if int(length) > MAX_REQUEST_BYTES:
                raise CvUploadError("batch_too_large", 413)
        bounded = Request(request.scope, receive=bounded_receive)
        async with bounded.form(max_files=20, max_fields=1, max_part_size=1024) as form:
            references, files = form.getlist("job_reference"), form.getlist("files")
            if set(form) - {"job_reference", "files"} or len(references) != 1 or not isinstance(references[0], str):
                raise CvUploadError("invalid_multipart")
            if any(not isinstance(file, UploadFile) for file in files):
                raise CvUploadError("invalid_multipart")
            service = CvUploadService(settings.cv_upload_root)
            return await run_in_threadpool(service.store_batch, references[0], files)
    except CvUploadError as error:
        return JSONResponse(status_code=error.status,
            content={"code": error.code, "message": PUBLIC_ERRORS[error.code]})
    except HTTPException as error:
        # Inspect only the parser's fixed count marker; never echo raw details.
        too_many_files = isinstance(error.detail, str) and error.detail.startswith("Too many files.")
        code = "batch_too_large" if exceeded else "invalid_batch" if too_many_files else "invalid_multipart"
        return JSONResponse(status_code=413 if exceeded else 400,
            content={"code": code, "message": PUBLIC_ERRORS[code]})
    except Exception:
        return JSONResponse(status_code=500,
            content={"code": "storage_failed", "message": PUBLIC_ERRORS["storage_failed"]})
