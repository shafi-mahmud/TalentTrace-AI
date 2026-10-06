import unicodedata
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.rag.contracts import CitationId, Heading, PolicyTitle


class EmploymentType(str, Enum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"


class WorkArrangement(str, Enum):
    ON_SITE = "on_site"
    HYBRID = "hybrid"
    REMOTE = "remote"


JobTitle = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=120),
]
RoleSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=1_000),
]
Department = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=100),
]
Location = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=150),
]
SeniorityLevel = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=50),
]
Responsibility = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=300),
]
Skill = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
]
EducationRequirement = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=200),
]
ExperienceYears = Annotated[int, Field(strict=True, ge=0, le=50)]
GeneratedSummary = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=20, max_length=2_000),
]
GeneratedQualification = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=300),
]
ModelName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]


def _contains_unsafe_control_character(value: str) -> bool:
    return any(unicodedata.category(character) in {"Cc", "Cs"} for character in value)


class JobDescriptionGenerationRequest(BaseModel):
    """Validated recruiter input for future job-description generation."""

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
    )

    job_title: JobTitle
    role_summary: RoleSummary
    responsibilities: list[Responsibility] = Field(min_length=1, max_length=20)
    required_skills: list[Skill] = Field(min_length=1, max_length=30)

    department: Department | None = None
    employment_type: EmploymentType | None = None
    work_arrangement: WorkArrangement | None = None
    location: Location | None = None
    seniority_level: SeniorityLevel | None = None
    preferred_skills: list[Skill] = Field(default_factory=list, max_length=30)
    minimum_experience_years: ExperienceYears | None = None
    education_requirements: list[EducationRequirement] = Field(
        default_factory=list,
        max_length=10,
    )

    @field_validator(
        "job_title",
        "role_summary",
        "department",
        "location",
        "seniority_level",
    )
    @classmethod
    def reject_unsafe_control_characters_in_text(cls, value: str | None) -> str | None:
        if value is not None and _contains_unsafe_control_character(value):
            raise ValueError("must not contain null or control characters")
        return value

    @field_validator(
        "responsibilities",
        "required_skills",
        "preferred_skills",
        "education_requirements",
    )
    @classmethod
    def validate_text_list(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        if any(_contains_unsafe_control_character(value) for value in values):
            raise ValueError("items must not contain null or control characters")

        normalized_values = [value.casefold() for value in values]
        if len(normalized_values) != len(set(normalized_values)):
            field_name = info.field_name
            raise ValueError(f"{field_name} must not contain duplicate values")

        return values

    @model_validator(mode="after")
    def reject_preferred_skills_already_required(self) -> "JobDescriptionGenerationRequest":
        required = {skill.casefold() for skill in self.required_skills}
        overlap = required.intersection(skill.casefold() for skill in self.preferred_skills)

        if overlap:
            raise ValueError("preferred_skills must not duplicate required_skills")

        return self


class GeneratedJobDescriptionDraft(BaseModel):
    """Strict structured draft returned by the configured LLM provider."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
    )

    title: JobTitle
    summary: GeneratedSummary
    responsibilities: list[Responsibility] = Field(min_length=1, max_length=20)
    required_skills: list[Skill] = Field(min_length=1, max_length=30)
    preferred_skills: list[Skill] = Field(max_length=30)
    qualifications: list[GeneratedQualification] = Field(min_length=1, max_length=10)
    policy_citation_ids: list[CitationId] = Field(min_length=1, max_length=4)

    @field_validator(
        "title",
        "summary",
    )
    @classmethod
    def reject_unsafe_control_characters_in_generated_text(cls, value: str) -> str:
        if _contains_unsafe_control_character(value):
            raise ValueError("must not contain null or control characters")
        return value

    @field_validator(
        "responsibilities",
        "required_skills",
        "preferred_skills",
        "qualifications",
        "policy_citation_ids",
    )
    @classmethod
    def validate_generated_lists(
        cls,
        values: list[str],
        info: ValidationInfo,
    ) -> list[str]:
        if any(_contains_unsafe_control_character(value) for value in values):
            raise ValueError("items must not contain null or control characters")

        normalized_values = [value.casefold() for value in values]
        if len(normalized_values) != len(set(normalized_values)):
            raise ValueError(f"{info.field_name} must not contain duplicate values")

        return values


class PolicyGroundingCitation(BaseModel):
    """Safe citation metadata assembled from trusted retrieval results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    citation_id: CitationId
    source_title: PolicyTitle
    heading_paths: tuple[tuple[Heading, ...], ...] = ()


class JobDescriptionGenerationResponse(BaseModel):
    """Public response for one generated, unapproved job-description draft."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["draft"] = "draft"
    human_review_required: Literal[True] = True
    retrieval_mode: Literal["deterministic_lexical_demo"] = (
        "deterministic_lexical_demo"
    )
    provider: Literal["groq"] = "groq"
    model: ModelName
    job_description: GeneratedJobDescriptionDraft
    grounding_citations: list[PolicyGroundingCitation] = Field(
        min_length=1,
        max_length=4,
    )
