"""Safe identifiers and upload metadata; no candidate content or server paths."""
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

JobReference = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=23, max_length=23,
    pattern=r"^TT-JOB-[A-F0-9]{16}$",
)]


class CvBatchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    job_reference: JobReference


class CvUploadItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    upload_id: UUID
    file_type: Literal["pdf", "docx"]
    size_bytes: int = Field(gt=0, le=10 * 1024 * 1024)


class CvUploadResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["uploaded"] = "uploaded"
    job_reference: JobReference
    batch_id: UUID
    accepted_count: int = Field(ge=1, le=20)
    files: tuple[CvUploadItem, ...] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def consistent_count(self):
        if self.accepted_count != len(self.files):
            raise ValueError("Upload count must match the returned metadata.")
        return self
