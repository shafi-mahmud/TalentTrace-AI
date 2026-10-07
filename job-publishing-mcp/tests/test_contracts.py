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


@pytest.mark.parametrize("field", ["job_reference", "title", "summary", "responsibilities", "required_skills", "qualifications"])
def test_missing_required_field(job_data, field):
    del job_data[field]
    with pytest.raises(ValidationError):
        JobCircular(**job_data)


def test_optional_application_url_accepts_https_and_preserves_old_clients(job_data):
    assert JobCircular(**job_data).application_url is None
    url="https://docs.google.com/forms/d/e/synthetic-test-form/viewform"
    assert JobCircular(**job_data,application_url=url).application_url==url


@pytest.mark.parametrize("url", ["not-a-url","http://example.invalid/form","https://user:password@example.invalid/form","https://user@example.invalid/form","https://localhost/form","https://10.0.0.1/form","javascript:alert(1)","https://example.invalid/%0a","https://example.invalid/form\x00","https://example.invalid/"+"x"*2049,123])
def test_invalid_application_url_is_rejected(job_data,url):
    with pytest.raises(ValidationError):
        JobCircular(**job_data,application_url=url)


@pytest.mark.parametrize("value", ["TT-JOB-0001", "BACKEND-AI-001", "TT-JOB-30BB2CDF9A5CCCA9"])
def test_valid_job_reference(job_data, value):
    assert JobCircular(**{**job_data, "job_reference": value}).job_reference == value


@pytest.mark.parametrize("value", ["", "x" * 41, "A" * 41, "lower-case", "A B", "A/B", "A\nB", "A\x00B", "A--B", 123, None])
def test_invalid_job_reference(job_data, value):
    with pytest.raises(ValidationError):
        JobCircular(**{**job_data, "job_reference": value})
