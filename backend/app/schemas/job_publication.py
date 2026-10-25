"""Bounded HTTP publication DTO mapped to the standalone MCP JobCircular."""
from uuid import UUID
import hashlib
import json
from typing import Annotated, Literal
import unicodedata
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints, PrivateAttr, model_validator


def plain_text(value: object) -> object:
    if isinstance(value, str):
        if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\n\t" for c in value) or "<" in value or ">" in value:
            raise ValueError("Invalid publication text.")
        return " ".join(value.split())
    return value


def single_line(value: object) -> object:
    if isinstance(value, str) and any(c in value for c in "\r\n\t"):
        raise ValueError("Expected single-line publication text.")
    return plain_text(value)


Title = Annotated[str, BeforeValidator(single_line), StringConstraints(min_length=1, max_length=200)]
Summary = Annotated[str, BeforeValidator(plain_text), StringConstraints(min_length=1, max_length=3000)]
Item = Annotated[str, BeforeValidator(plain_text), StringConstraints(min_length=1, max_length=300)]
Skill = Annotated[str, BeforeValidator(single_line), StringConstraints(min_length=1, max_length=100)]
Location = Annotated[str, BeforeValidator(single_line), StringConstraints(min_length=1, max_length=120)]


class RecruiterPublishRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    job_id: Annotated[UUID | None, BeforeValidator(lambda value: UUID(value) if isinstance(value, str) else value)] = None
    destination: Literal["discord", "telegram"] = "discord"
    _job_reference: str | None = PrivateAttr(default=None)
    title: Title
    summary: Summary
    responsibilities: list[Item] = Field(min_length=1, max_length=15)
    required_skills: list[Skill] = Field(min_length=1, max_length=20)
    preferred_skills: list[Skill] = Field(default_factory=list, max_length=20)
    qualifications: list[Item] = Field(min_length=1, max_length=15)
    location: Location | None = None
    employment_type: Literal["full_time", "part_time", "contract", "internship", "temporary"] | None = None
    work_arrangement: Literal["on_site", "remote", "hybrid"] | None = None

    def mcp_job(self) -> dict:
        job = self.model_dump(mode="json", exclude={"job_id", "destination"})
        if job["work_arrangement"] == "on_site":
            job["work_arrangement"] = "onsite"
        # Temporary demo identity: stable for normalized content, not a database ID.
        canonical = json.dumps(job, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        job["job_reference"] = self._job_reference or "TT-JOB-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16].upper()
        return job


class PublicationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, hide_input_in_errors=True)
    destination: Literal["discord", "telegram"]
    status: Literal["published"]
    external_id: Annotated[str, StringConstraints(pattern=r"^[1-9][0-9]{0,19}$")]

    @model_validator(mode="after")
    def valid_destination_receipt(self):
        if self.destination == "discord" and not 17 <= len(self.external_id) <= 20:
            raise ValueError("Invalid Discord receipt.")
        return self
