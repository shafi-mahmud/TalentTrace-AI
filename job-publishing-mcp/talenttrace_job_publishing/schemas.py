"""Bounded plain-text contracts, independent from the FastAPI application."""

from typing import Annotated, Literal
import unicodedata

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, StringConstraints
from .urls import validate_application_url


def normalize_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    if any(
        unicodedata.category(char) in {"Cc", "Cf", "Cs"} and char not in "\n\t"
        for char in value
    ):
        raise ValueError("Text contains unsupported control characters.")
    # This contract is plain text: no HTML, scripts or Discord angle-bracket markup.
    if "<" in value or ">" in value:
        raise ValueError("Use plain text without markup.")
    return " ".join(value.split())


def single_line(value: object) -> object:
    if isinstance(value, str) and any(char in value for char in "\r\n\t"):
        raise ValueError("Use single-line text.")
    return normalize_text(value)


Title = Annotated[
    str, BeforeValidator(single_line), StringConstraints(min_length=1, max_length=200)
]
Summary = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=3000)
]
Item = Annotated[
    str, BeforeValidator(normalize_text), StringConstraints(min_length=1, max_length=300)
]
Skill = Annotated[
    str, BeforeValidator(single_line), StringConstraints(min_length=1, max_length=100)
]
Location = Annotated[
    str, BeforeValidator(single_line), StringConstraints(min_length=1, max_length=120)
]


JobReference = Annotated[
    str, BeforeValidator(single_line),
    StringConstraints(min_length=1, max_length=40, pattern=r"^[A-Z0-9]+(?:-[A-Z0-9]+)*$"),
]


ApplicationURL = Annotated[str, BeforeValidator(validate_application_url)]


class JobCircular(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, hide_input_in_errors=True)

    job_reference: JobReference
    title: Title
    summary: Summary
    responsibilities: list[Item] = Field(min_length=1, max_length=15)
    required_skills: list[Skill] = Field(min_length=1, max_length=20)
    preferred_skills: list[Skill] = Field(default_factory=list, max_length=20)
    qualifications: list[Item] = Field(min_length=1, max_length=15)
    location: Location | None = None
    application_url: ApplicationURL | None = None
    employment_type: Literal[
        "full_time", "part_time", "contract", "internship", "temporary"
    ] | None = None
    work_arrangement: Literal["onsite", "remote", "hybrid"] | None = None


class PublishJobResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, hide_input_in_errors=True)

    destination: Literal["discord"] = "discord"
    status: Literal["published"] = "published"
    external_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{17,20}$")]
