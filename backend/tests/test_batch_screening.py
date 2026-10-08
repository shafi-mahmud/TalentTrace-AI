"""Synthetic API integration; actual parsers/graph, mocked external providers."""
import asyncio
from uuid import uuid4

import httpx
import pytest

from app.api.routers import screening as route, cv_uploads
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.core.config import Settings
from app.integrations.llm.candidate_profile import CandidateParserNotConfigured
from app.main import app
from app.schemas.batch_screening import ReviewedJobSnapshot
from app.schemas.candidate_profile import CandidateContact, CandidateProfile
from app.schemas.job_description import JobDescriptionGenerationRequest
from app.services.batch_screening import BatchScreeningService, screening_suggestions
from app.services.candidate_profile import CandidateProfileService
from app.services.cv_extraction import CvExtractionError
from test_candidate_profile import FakeExtractor, SOURCE
from test_cv_extraction import pdf_bytes
from test_screening_matching import FakeMatcher, request as screening_input, semantic_result
from test_recruiter_chat import FakeInterpreter, RecordingWorkflow, MESSAGE
from app.services.recruiter_chat import RecruiterChatService
from app.schemas.recruiter_chat import RecruiterChatRequest

REFERENCE = "TT-JOB-0123456789ABCDEF"


def snapshot(**changes):
    return {"job_reference": REFERENCE, "job_title": "Backend Engineer", "criteria_confirmed": True,
        "criteria": [{"criterion_id": "python", "description": "Python", "category": "skill", "is_hard": True}], **changes}


def candidate(status="parsed", skills=("Python",)):
    supplied = screening_input(skills=skills, status=status)
    return CandidateProfile(upload_id=supplied.upload_id, parsing_status=status,
        qualifications=supplied.qualifications,
        contact=CandidateContact(candidate_name=None, emails=[], phones=[], links=[], location=None) if status == "parsed" else None)


class Profiles:
    def __init__(self, values): self.values, self.calls = values, []
    async def parse_batch(self, job_reference, batch_id):
        self.calls.append((job_reference, batch_id))
        return tuple(self.values)


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch):
    async def forbidden(*args, **kwargs): pytest.fail("Tests must not call external providers.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


def post(payload=None, job_reference=REFERENCE, batch_id=None):
    async def send():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(f"/api/v1/cv-uploads/{job_reference}/{batch_id or uuid4()}/screen",
                json=payload if payload is not None else snapshot())
    return asyncio.run(send())


@pytest.mark.parametrize("status,outcome", [("supported", "eligible"), ("not_found", "excluded"), ("ambiguous", "insufficient_evidence")])
def test_real_screening_graph_semantic_outcomes_and_ocr_evidence(monkeypatch, status, outcome):
    profile = candidate(skills=("Django",))
    profile.qualifications.skills[0] = profile.qualifications.skills[0].model_copy(update={
        "source": profile.qualifications.skills[0].source.model_copy(update={"method": "ocr"})})
    evidence = [] if status == "not_found" else [{"fact_id": "fact:0001", "value": "Django"}]
    matcher = FakeMatcher([semantic_result(identifier="python", status=status, evidence=evidence)])
    profiles = Profiles([profile])
    service = BatchScreeningService(profiles, CandidateScreeningWorkflow(matcher))
    monkeypatch.setattr(route, "BatchScreeningService", lambda: service)
    response = post()
    assert response.status_code == 200
    result = response.json()["candidates"][0]["result"]
    assert result["screening_decision"] == outcome
    assert result["matching_result"]["matches"][0]["match_method"] == "semantic"
    if evidence:
        assert result["matching_result"]["matches"][0]["evidence"][0]["source"]["method"] == "ocr"
    assert len(matcher.calls) == 1 and len(profiles.calls) == 1
    assert "contact" not in response.text and "qualifications" not in response.text
    assert not any(name in response.json() for name in ["score", "rank"])
    ranking = response.json()["ranking"]
    assert len(ranking) == (1 if outcome == "eligible" else 0)
    if ranking:
        assert ranking[0]["supported_count"] == ranking[0]["rank"] == 1
        assert ranking[0]["upload_id"] == str(profile.upload_id)


def test_batch_isolates_source_provider_and_unexpected_candidate_failures(monkeypatch):
    values = [candidate(), candidate("parsing_failed"), candidate(skills=("Other",)), candidate(), candidate()]
    matcher = FakeMatcher(error=RuntimeError("PRIVATE_PROVIDER_DETAILS"))
    class Workflow(CandidateScreeningWorkflow):
        async def screen(self, supplied):
            assert set(supplied.model_dump()) == {"job_reference", "upload_id", "parsing_status", "qualifications", "criteria"}
            if supplied.upload_id == values[3].upload_id: raise RuntimeError("PRIVATE_EXCEPTION_PATH")
            return await super().screen(supplied)
    monkeypatch.setattr(route, "BatchScreeningService", lambda: BatchScreeningService(Profiles(values), Workflow(matcher)))
    response = post()
    assert response.status_code == 200
    rows = response.json()["candidates"]
    assert [row["result"]["status"] if row["result"] else row["error_code"] for row in rows] == [
        "decision_complete", "source_unavailable", "matching_failed", "screening_processing_failed", "decision_complete"]
    assert rows[0]["result"]["screening_decision"] == rows[-1]["result"]["screening_decision"] == "eligible"
    assert rows[1]["result"]["screening_decision"] is None and rows[2]["result"]["screening_decision"] is None
    assert "PRIVATE" not in response.text
    ranking = response.json()["ranking"]
    assert {r["upload_id"] for r in ranking} == {str(values[0].upload_id), str(values[-1].upload_id)}
    assert all(r["rank"] == 1 and r["tied"] for r in ranking)


@pytest.mark.parametrize("confirmation", [False, None, "true", 1])
def test_confirmation_must_be_explicit_boolean_true(monkeypatch, confirmation):
    monkeypatch.setattr(route, "BatchScreeningService", lambda: pytest.fail("Invalid input must not run"))
    assert post(snapshot(criteria_confirmed=confirmation)).status_code == 422


@pytest.mark.parametrize("change", [
    {"criteria_confirmed": "missing"}, {"candidate_qualifications": {"skills": ["PRIVATE_TEXT"]}},
    {"screening_decision": "eligible"}, {"api_key": "PRIVATE_TEXT"}, {"criteria": []},
    {"criteria": [{"criterion_id": "x", "description": "PRIVATE_TEXT\x00", "category": "skill", "is_hard": True}]},
    {"criteria": [{"criterion_id": "x", "description": "Python", "category": "invalid", "is_hard": True}]},
    {"criteria": [{"criterion_id": "x", "description": "Python", "category": "skill"}]},
    {"criteria": [{"criterion_id": "x", "description": "Python", "category": "skill", "is_hard": "true"}]},
])
def test_malformed_requests_are_rejected_without_echo(monkeypatch, change):
    monkeypatch.setattr(route, "BatchScreeningService", lambda: pytest.fail("Invalid input must not run"))
    payload = snapshot(**change)
    if change.get("criteria_confirmed") == "missing": payload.pop("criteria_confirmed")
    response = post(payload)
    assert response.status_code == 422 and "PRIVATE_TEXT" not in response.text


def test_duplicate_and_oversized_criteria_rejected():
    c = snapshot()["criteria"][0]
    for rows in ([c, {**c, "criterion_id": "PYTHON"}], [{**c, "criterion_id": f"x{i}"} for i in range(51)]):
        assert post(snapshot(criteria=rows)).status_code == 422


def test_job_mismatch_rejected_before_parsing(monkeypatch):
    profiles = Profiles([candidate()])
    monkeypatch.setattr(route, "BatchScreeningService", lambda: BatchScreeningService(profiles))
    response = post(job_reference="TT-JOB-FFFFFFFFFFFFFFFF")
    assert response.status_code == 409 and not profiles.calls


@pytest.mark.parametrize("error,status", [(CandidateParserNotConfigured(), 503),
    (CvExtractionError("batch_not_found", 404), 404), (RuntimeError("PRIVATE_PATH_SECRET"), 500)])
def test_request_level_errors_sanitized(monkeypatch, error, status):
    class FailedProfiles:
        async def parse_batch(self, *args): raise error
    monkeypatch.setattr(route, "BatchScreeningService", lambda: BatchScreeningService(FailedProfiles()))
    response = post()
    assert response.status_code == status and "PRIVATE" not in response.text


def test_suggestions_use_recruiter_requirements_and_never_approve_hard_flags():
    supplied = JobDescriptionGenerationRequest(job_title="Backend Engineer", role_summary="Build reliable backend services.",
        responsibilities=["Build APIs"], required_skills=["Python"], preferred_skills=["FastAPI"],
        education_requirements=["Computer Science degree"], minimum_experience_years=2)
    result = screening_suggestions(supplied)
    assert [c.category for c in result.criteria] == ["skill", "skill", "education", "experience"]
    assert not any(c.is_hard for c in result.criteria)
    assert result.criteria[0].description == "Python" and result.criteria[1].description == "FastAPI"


def test_chat_response_retains_only_original_requirements_as_suggestions():
    workflow = RecordingWorkflow()
    response = asyncio.run(RecruiterChatService(FakeInterpreter(), workflow_factory=lambda: workflow).respond(
        RecruiterChatRequest(message=MESSAGE)))
    assert [c.description for c in response.screening_suggestions.criteria] == ["Python", "FastAPI"]
    assert not any(c.is_hard for c in response.screening_suggestions.criteria)


def test_confirmed_preferred_requirement_cannot_exclude(monkeypatch):
    payload = snapshot()
    payload["criteria"][0]["is_hard"] = False
    monkeypatch.setattr(route, "BatchScreeningService", lambda: BatchScreeningService(Profiles([candidate(skills=())])))
    response = post(payload)
    assert response.status_code == 200
    result = response.json()["candidates"][0]["result"]
    assert result["screening_decision"] == "eligible"
    assert result["matching_result"]["matches"][0]["match_status"] == "not_found"


def test_actual_upload_pdf_parse_and_screen_endpoint(monkeypatch, tmp_path):
    config = Settings(_env_file=None, groq_api_key="synthetic-unit-test-key", cv_upload_root=tmp_path / "private")
    extractor = FakeExtractor()
    monkeypatch.setattr(cv_uploads, "settings", config)
    profiles = CandidateProfileService(config, extractor=extractor)
    matcher = FakeMatcher(error=AssertionError("Exact Python must bypass semantic provider"))
    monkeypatch.setattr(route, "BatchScreeningService", lambda: BatchScreeningService(profiles, CandidateScreeningWorkflow(matcher)))
    content = pdf_bytes((SOURCE,))
    async def execute():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            uploaded = await client.post("/api/v1/cv-uploads", data={"job_reference": REFERENCE},
                files=[("files", ("synthetic.pdf", content, "application/pdf")),
                    ("files", ("unreadable.pdf", b"%PDF-1.4\nbroken\n%%EOF", "application/pdf"))])
            assert uploaded.status_code == 201
            other = "TT-JOB-FFFFFFFFFFFFFFFF"
            wrong = await client.post(f"/api/v1/cv-uploads/{other}/{uploaded.json()['batch_id']}/screen", json=snapshot(job_reference=other))
            assert wrong.status_code == 404 and not extractor.calls
            response = await client.post(f"/api/v1/cv-uploads/{REFERENCE}/{uploaded.json()['batch_id']}/screen", json=snapshot())
            return uploaded.json(), response
    uploaded, response = asyncio.run(execute())
    assert response.status_code == 200
    results = response.json()["candidates"]
    assert sorted(row["result"]["status"] for row in results) == ["decision_complete", "source_unavailable"]
    assert len(extractor.calls) == 1 and not matcher.calls
    assert {c["upload_id"] for c in results} == {f["upload_id"] for f in uploaded["files"]}
    paths = list((config.cv_upload_root / REFERENCE / uploaded["batch_id"]).iterdir())
    assert any(path.read_bytes() == content for path in paths)
    assert response.json()["snapshot"] == snapshot()
