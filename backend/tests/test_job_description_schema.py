import pytest
from pydantic import ValidationError

from app.schemas.job_description import (
    EmploymentType,
    JobDescriptionGenerationRequest,
    WorkArrangement,
)


def minimal_request_data() -> dict[str, object]:
    return {
        "job_title": "Backend Engineer",
        "role_summary": "Build and maintain reliable backend services for TalentTrace AI.",
        "responsibilities": ["Develop well-tested FastAPI endpoints"],
        "required_skills": ["Python"],
    }


def test_valid_minimal_request() -> None:
    request = JobDescriptionGenerationRequest.model_validate(minimal_request_data())

    assert request.job_title == "Backend Engineer"
    assert request.preferred_skills == []
    assert request.education_requirements == []
    assert request.minimum_experience_years is None


def test_valid_complete_request_strips_surrounding_whitespace() -> None:
    request = JobDescriptionGenerationRequest.model_validate(
        {
            "job_title": "  Backend Engineer  ",
            "role_summary": "  Build and maintain secure backend services for TalentTrace AI.  ",
            "responsibilities": [
                "  Design maintainable API contracts  ",
                "Review backend changes",
            ],
            "required_skills": ["  Python  ", "FastAPI"],
            "department": "  Engineering  ",
            "employment_type": "full_time",
            "work_arrangement": "hybrid",
            "location": "  Dhaka  ",
            "seniority_level": "  Mid-level  ",
            "preferred_skills": ["PostgreSQL", "Docker"],
            "minimum_experience_years": 3,
            "education_requirements": [
                "  Bachelor's degree or equivalent experience  "
            ],
        }
    )

    assert request.job_title == "Backend Engineer"
    assert request.responsibilities[0] == "Design maintainable API contracts"
    assert request.required_skills[0] == "Python"
    assert request.department == "Engineering"
    assert request.location == "Dhaka"
    assert request.seniority_level == "Mid-level"
    assert request.education_requirements == [
        "Bachelor's degree or equivalent experience"
    ]
    assert request.employment_type is EmploymentType.FULL_TIME
    assert request.work_arrangement is WorkArrangement.HYBRID


@pytest.mark.parametrize(
    "missing_field",
    ["job_title", "role_summary", "responsibilities", "required_skills"],
)
def test_missing_required_fields_are_rejected(missing_field: str) -> None:
    data = minimal_request_data()
    data.pop(missing_field)

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("job_title", "   "),
        ("role_summary", "\t"),
        ("responsibilities", ["   "]),
        ("required_skills", ["   "]),
    ],
)
def test_blank_required_fields_are_rejected(
    field_name: str,
    invalid_value: object,
) -> None:
    data = minimal_request_data()
    data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("job_title", "J" * 121),
        ("role_summary", "S" * 1_001),
        ("responsibilities", [f"Responsibility {number}" for number in range(21)]),
        ("responsibilities", ["R" * 301]),
        ("required_skills", [f"Skill {number}" for number in range(31)]),
        ("required_skills", ["S" * 101]),
        ("department", "D" * 101),
        ("location", "L" * 151),
        ("seniority_level", "S" * 51),
        ("preferred_skills", [f"Preferred {number}" for number in range(31)]),
        (
            "education_requirements",
            [f"Education requirement {number}" for number in range(11)],
        ),
        ("education_requirements", ["E" * 201]),
    ],
)
def test_excessive_string_and_list_lengths_are_rejected(
    field_name: str,
    invalid_value: object,
) -> None:
    data = minimal_request_data()
    data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("employment_type", "permanent"),
        ("work_arrangement", "flexible"),
    ],
)
def test_invalid_enum_values_are_rejected(
    field_name: str,
    invalid_value: str,
) -> None:
    data = minimal_request_data()
    data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize("invalid_value", [-1, 51, True])
def test_invalid_experience_range_is_rejected(invalid_value: object) -> None:
    data = minimal_request_data()
    data["minimum_experience_years"] = invalid_value

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "duplicate_values"),
    [
        ("responsibilities", ["Write APIs", "  write apis  "]),
        ("required_skills", ["Python", "python"]),
        ("preferred_skills", ["Docker", "DOCKER"]),
        (
            "education_requirements",
            ["Bachelor's degree", "BACHELOR'S DEGREE"],
        ),
    ],
)
def test_case_insensitive_duplicates_within_lists_are_rejected(
    field_name: str,
    duplicate_values: list[str],
) -> None:
    data = minimal_request_data()
    data[field_name] = duplicate_values

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


def test_preferred_skills_cannot_duplicate_required_skills() -> None:
    data = minimal_request_data()
    data["preferred_skills"] = ["  PYTHON  "]

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


def test_unknown_fields_are_rejected() -> None:
    data = minimal_request_data()
    data["unexpected_field"] = "unexpected value"

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize(
    "forbidden_field",
    ["provider", "model", "api_key", "prompt", "system_instruction", "configuration"],
)
def test_configuration_style_fields_are_rejected(forbidden_field: str) -> None:
    data = minimal_request_data()
    data[forbidden_field] = "client-controlled value"

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("job_title", "Backend\x00Engineer"),
        (
            "role_summary",
            "Build reliable backend\x07 services for TalentTrace AI.",
        ),
        ("responsibilities", ["Build secure\x00 APIs"]),
        ("required_skills", ["Python\x1f"]),
    ],
)
def test_null_and_control_characters_are_rejected(
    field_name: str,
    invalid_value: object,
) -> None:
    data = minimal_request_data()
    data[field_name] = invalid_value

    with pytest.raises(ValidationError):
        JobDescriptionGenerationRequest.model_validate(data)
