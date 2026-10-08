"""Preparation contracts only: no contact identity, matching or verdicts."""
import unicodedata
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from app.schemas.candidate_profile import CandidateQualifications, ProfileContract
from app.schemas.cv_upload import JobReference

CriterionId = Annotated[str, StringConstraints(
    min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$",
)]
CriterionDescription = Annotated[str, StringConstraints(
    strip_whitespace=True, min_length=1, max_length=500,
)]


class ScreeningCriterion(ProfileContract):
    criterion_id: CriterionId
    category: Literal["skill", "experience", "education"]
    description: CriterionDescription = Field(repr=False)
    is_hard: bool

    @field_validator("description", mode="before")
    @classmethod
    def single_line_description(cls, value):
        if isinstance(value, str) and any(
            unicodedata.category(char) in {"Cc", "Cf", "Cs"} for char in value
        ):
            raise ValueError("Criterion descriptions must be safe single-line text.")
        return value


class ScreeningInput(ProfileContract):
    job_reference: JobReference
    upload_id: UUID
    # Same three statuses as CandidateProfile; no new parsing semantics.
    parsing_status: Literal["parsed", "source_unavailable", "parsing_failed"]
    qualifications: CandidateQualifications | None = Field(repr=False)
    criteria: tuple[ScreeningCriterion, ...] = Field(min_length=1, max_length=50, repr=False)

    @model_validator(mode="after")
    def consistent_input(self):
        if (self.parsing_status == "parsed") != (self.qualifications is not None):
            raise ValueError("Qualifications must be present only for parsed candidates.")
        ids = [item.criterion_id.casefold() for item in self.criteria]
        if len(ids) != len(set(ids)):
            raise ValueError("Criterion identifiers must be unique.")
        return self


class RequirementContext(ProfileContract):
    """Stable category grouping; IDs identify requirements, not satisfaction."""
    skill_ids: tuple[CriterionId, ...] = Field(max_length=50)
    experience_ids: tuple[CriterionId, ...] = Field(max_length=50)
    education_ids: tuple[CriterionId, ...] = Field(max_length=50)
    hard_requirement_ids: tuple[CriterionId, ...] = Field(max_length=50)

    @model_validator(mode="after")
    def consistent_ids(self):
        ids = self.skill_ids + self.experience_ids + self.education_ids
        if not ids or len(ids) > 50 or len(set(ids)) != len(ids):
            raise ValueError("Requirement groups must contain unique bounded identifiers.")
        if (len(set(self.hard_requirement_ids)) != len(self.hard_requirement_ids)
                or not set(self.hard_requirement_ids).issubset(ids)):
            raise ValueError("Hard requirements must belong to the requirement groups.")
        return self


class ScreeningPreparationResult(ProfileContract):
    job_reference: JobReference
    upload_id: UUID
    status: Literal["ready_for_matching", "source_unavailable"]
    parsing_status: Literal["parsed", "source_unavailable", "parsing_failed"]
    requirement_context: RequirementContext
    screening_decision: None = None

    @model_validator(mode="after")
    def consistent_status(self):
        if (self.status == "ready_for_matching") != (self.parsing_status == "parsed"):
            raise ValueError("Preparation status must match source readiness.")
        return self
