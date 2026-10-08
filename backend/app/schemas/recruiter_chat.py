"""Single-turn recruiter chat and internal extraction contracts."""

import re
import unicodedata
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.schemas.job_description import ExperienceYears, JobDescriptionGenerationResponse, Location, EmploymentType, WorkArrangement
from app.schemas.batch_screening import ScreeningSuggestions


ClarificationField = Literal["job_title", "role_summary", "responsibilities", "required_skills", "department", "employment_type", "work_arrangement", "location", "seniority_level", "preferred_skills", "minimum_experience_years", "education_requirements"]
FIELD_LABELS = {name: name.replace("_", " ") for name in ClarificationField.__args__}
FIELD_LABELS["role_summary"] = "role purpose or summary"


def safe_text(value: str) -> str:
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} and c not in "\r\n\t" for c in value):
        raise ValueError("Use text without unsafe control characters.")
    return unicodedata.normalize("NFC", value).replace("\r\n", "\n").replace("\r", "\n")


class RecruiterChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)
    message: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]

    @field_validator("message", mode="before")
    @classmethod
    def validate_plain_recruiter_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        value = safe_text(value)
        patterns = [
            r"\b[^\s@]+@[^\s@]+\.[^\s@]+\b",
            r"(?<!\w)\+?\d[\d ()-]{8,}\d(?!\w)",
            r"\b(?:candidate|applicant)\s+(?:cv|resume)\s+(?:details|attached|submission|for review)\b",
            r"\b(?:here is|here are|attached is)\s+(?:a |the )?(?:candidate |applicant )?(?:cv|resume)\b",
            r"\b(?:my|the candidate['’]s|the applicant['’]s)\s+(?:cv|resume)\b",
            r"\b(?:submit|upload|share|attach)\w*\s+(?:a |the |this |their |his |her )?(?:(?:candidate|applicant)(?:['’]s)? )?(?:cv|resume)\b",
        ]
        names = r"\b(?i:candidate|applicant)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b|\b[A-Z][a-z]+\s+[A-Z][a-z]+['’]s\s+(?:CV|cv|resume)\b"
        if any(re.search(pattern, value, re.I) for pattern in patterns) or re.search(names, value):
            raise ValueError("Use job requirements only, without candidate information.")
        return value


class TextEvidence(BaseModel):
    """Copied evidence plus a minimally normalized value; never polished prose."""
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    value: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

    @field_validator("value", "evidence")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return safe_text(value)


class ExperienceEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)
    value: ExperienceYears
    evidence: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]

    @field_validator("evidence")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return safe_text(value)


class ExtractedJobRequirements(BaseModel):
    """All provider properties required; null/[] means absent. JD validates bounds."""
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    job_title: TextEvidence | None
    role_summary: TextEvidence | None
    responsibilities: list[TextEvidence] = Field(max_length=20)
    required_skills: list[TextEvidence] = Field(max_length=30)
    department: TextEvidence | None
    employment_type: TextEvidence | None
    work_arrangement: TextEvidence | None
    location: TextEvidence | None
    seniority_level: TextEvidence | None
    preferred_skills: list[TextEvidence] = Field(max_length=30)
    minimum_experience_years: ExperienceEvidence | None
    education_requirements: list[TextEvidence] = Field(max_length=10)


class RecruiterInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    intent: Literal["create_job_description", "unsupported"]
    requirements: ExtractedJobRequirements | None


class ClarificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["clarification"] = "clarification"
    intent: Literal["create_job_description"] = "create_job_description"
    assistant_message: str = Field(min_length=1, max_length=600)
    missing_fields: list[ClarificationField] = Field(min_length=1, max_length=12)


class UnsupportedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["unsupported"] = "unsupported"
    intent: Literal["unsupported"] = "unsupported"
    assistant_message: str = "I can help create a job description. Include the job title, role purpose, responsibilities and required skills. Publishing uses the draft action after review; candidate processing is unavailable."


class PublishingContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    location: Location | None = None
    employment_type: EmploymentType | None = None
    work_arrangement: WorkArrangement | None = None


class JobDescriptionChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["jd_generated"] = "jd_generated"
    intent: Literal["create_job_description"] = "create_job_description"
    assistant_message: str = "Your policy-grounded draft is ready. Please review it before publishing."
    job_description_result: JobDescriptionGenerationResponse
    publishing_context: PublishingContext = Field(default_factory=PublishingContext)
    screening_suggestions: ScreeningSuggestions | None = None


RecruiterChatResponse = Annotated[
    ClarificationResponse | UnsupportedResponse | JobDescriptionChatResponse,
    Field(discriminator="status"),
]
