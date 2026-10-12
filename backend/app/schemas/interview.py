"""Provider-independent scheduling; no contact data or client verdicts."""
from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.cv_upload import JobReference
from app.services.score_records import SCORING_VERSION

TimezoneName = Annotated[str, StringConstraints(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_+/-]+$")]


class InterviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    batch_id: UUID
    upload_id: UUID
    criteria_revision: int = Field(strict=True, ge=1)
    scoring_version: Literal["f2-coverage-v1"] = SCORING_VERSION
    selection_confirmed: Literal[True]
    confirm_eligible_unscored: bool = Field(default=False, strict=True)
    scheduled_at: AwareDatetime
    timezone: TimezoneName
    duration_minutes: int = Field(strict=True, ge=15, le=180)

    @field_validator("selection_confirmed", mode="before")
    @classmethod
    def explicit_selection(cls, value):
        if value is not True:
            raise ValueError("Explicit recruiter selection is required.")
        return value

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Use an available IANA timezone.") from None
        return value

    @field_validator("scheduled_at")
    @classmethod
    def utc_time(cls, value):
        return value.astimezone(timezone.utc)

    @field_validator("scheduled_at", mode="before")
    @classmethod
    def iso_timestamp(cls, value):
        if not isinstance(value, (str, datetime)):
            raise ValueError("Supply an ISO timestamp with a timezone offset.")
        return value


class InterviewResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    id: UUID
    job_id: UUID
    job_reference: JobReference
    batch_id: UUID
    upload_id: UUID
    criteria_revision: int = Field(ge=1)
    scoring_version: Literal["f2-coverage-v1"]
    scheduled_at: AwareDatetime
    timezone: TimezoneName
    duration_minutes: int = Field(ge=15, le=180)
    unscored_confirmed: bool
    status: Literal["scheduled"] = "scheduled"

    _valid_timezone = field_validator("timezone")(InterviewRequest.valid_timezone.__func__)
    _utc_time = field_validator("scheduled_at")(InterviewRequest.utc_time.__func__)
