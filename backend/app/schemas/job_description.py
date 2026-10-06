import unicodedata
from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
    model_validator,
)


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
