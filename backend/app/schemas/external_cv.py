"""Internal synthetic intake contracts; no source credentials or candidate identity."""
from typing import Annotated, Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, StringConstraints
from starlette.datastructures import UploadFile
from pydantic import Field, model_validator, ValidationError
from app.schemas.cv_upload import JobReference, CvUploadItem

SourceId = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_-]*$")]
SubmissionId = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")]


class ApprovedExternalSource(BaseModel):
    """Server/operator approval, never supplied by an external applicant."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    source_id: SourceId
    recruiter_id: UUID
    job_id: UUID


class ApplicationContact(BaseModel):
    """Validated source contact; respondent input is not mailbox verification."""
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    email: str | None = Field(default=None, max_length=254, repr=False)
    status: Literal["available", "missing", "invalid"]
    provenance: Literal["google_forms_collected_email"] = "google_forms_collected_email"
    collection_type: Literal["RESPONDER_INPUT"] = "RESPONDER_INPUT"
    validation_version: Literal[1] = 1

    @model_validator(mode="after")
    def consistent(self):
        if self.status == "available":
            import re
            if not self.email or len(self.email.split("@", 1)[0]) > 64 or not re.fullmatch(r"[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+", self.email):
                raise ValueError("Invalid application contact")
        elif self.email is not None:
            raise ValueError("Unavailable contact cannot contain an address")
        return self


def respondent_contact(value):
    if value is None or value == "":
        return ApplicationContact(status="missing")
    if not isinstance(value, str) or value != value.strip() or len(value) > 254:
        return ApplicationContact(status="invalid")
    try:
        local, domain = value.rsplit("@", 1)
        return ApplicationContact(email=local + "@" + domain.lower(), status="available")
    except (ValueError, ValidationError):
        return ApplicationContact(status="invalid")


class ExternalCvSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True, hide_input_in_errors=True)
    source_id: SourceId
    external_submission_id: SubmissionId
    source_job_reference: JobReference
    job_reference: JobReference
    synthetic: Literal[True]  # Caller explicitly attests synthetic fixtures; not a content detector.
    application_contact: ApplicationContact | None = Field(default=None, repr=False)
    cv: UploadFile = Field(exclude=True, repr=False)


class ExternalCvImportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    submission_id: UUID
    job_reference: JobReference
    batch_id: UUID
    file: CvUploadItem
    status: Literal["pending_review"] = "pending_review"
    created: bool
