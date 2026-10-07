import pytest
from pydantic import ValidationError

from talenttrace_job_publishing.schemas import JobCircular


def test_valid_minimal_circular_normalizes_whitespace(job_data):
    job_data["summary"] = "  Build\n secure   services.  "
    job = JobCircular(**job_data)
    assert job.title == "Backend AI Engineer"
    assert job.summary == "Build secure services."
    assert job.preferred_skills == []


def test_complete_circular(job_data):
    job = JobCircular(**job_data, preferred_skills=["SQL"], location="Dhaka", employment_type="full_time", work_arrangement="hybrid")
    assert job.location == "Dhaka"


@pytest.mark.parametrize("field", ["api_key", "webhook_url", "provider", "prompt", "candidate", "age", "gender"])
def test_extra_fields_rejected(job_data, field):
    with pytest.raises(ValidationError):
        JobCircular(**job_data, **{field: "not allowed"})


@pytest.mark.parametrize("field,value", [
    ("title", "   "), ("summary", ""), ("title", "x" * 201),
    ("title", "Multi\nline"), ("summary", "x" * 3001),
    ("summary", "unsafe\x00text"), ("summary", "unsafe\x1btext"),
    ("summary", "unsafe\u202etext"), ("summary", "<script>alert(1)</script>"),
    ("summary", "<b>HTML</b>"), ("responsibilities", []),
    ("responsibilities", ["x"] * 16), ("required_skills", ["x"] * 21),
    ("required_skills", ["x" * 101]), ("qualifications", ["x" * 301]),
    ("required_skills", [1]), ("title", 123), ("location", "x" * 121),
    ("employment_type", "unknown"), ("work_arrangement", "unknown"),
])
def test_invalid_circular(job_data, field, value):
    job_data[field] = value
    with pytest.raises(ValidationError):
        JobCircular(**job_data)


@pytest.mark.parametrize("field", ["title", "summary", "responsibilities", "required_skills", "qualifications"])
def test_missing_required_field(job_data, field):
    del job_data[field]
    with pytest.raises(ValidationError):
        JobCircular(**job_data)
