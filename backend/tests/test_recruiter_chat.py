import asyncio
import json

import httpx
import pytest
from groq import APITimeoutError
from pydantic import ValidationError

from app.agents.jd.errors import GenerationProviderError, GenerationTimeoutError, MissingGenerationConfigurationError
from app.agents.jd.workflow import JobDescriptionWorkflow
from app.api.routers import recruiter_chat as route
from app.integrations.llm.recruiter_chat import GroqRecruiterInstructionInterpreter
from app.main import app
from app.rag.retrieval import PolicyRetrievalError
from app.schemas.recruiter_chat import RecruiterChatRequest, RecruiterInterpretation
from app.services.recruiter_chat import RecruiterChatService
from test_groq_job_description import FakeCompletions, FakeGroqClient, configured_settings, policy_context
from test_job_descriptions_endpoint import successful_response
from app.integrations.llm.groq import JobDescriptionGenerationResult


MESSAGE = "Create a Backend Engineer JD. Build and maintain secure backend services. Responsibilities: Develop APIs; Write tests. Required skills: Python and FastAPI."


def evidence(value, source=None):
    return {"value": value, "evidence": source if source is not None else str(value)}


def extracted_data():
    return {
        "intent": "create_job_description",
        "requirements": {
            "job_title": evidence("Backend Engineer"),
            "role_summary": evidence("Build and maintain secure backend services."),
            "responsibilities": [evidence("Develop APIs"), evidence("Write tests")],
            "required_skills": [evidence("Python"), evidence("FastAPI")],
            "department": None, "employment_type": None, "work_arrangement": None,
            "location": None, "seniority_level": None, "preferred_skills": [],
            "minimum_experience_years": None, "education_requirements": [],
        },
    }


class FakeInterpreter:
    def __init__(self, data=None, error=None):
        self.data = data or extracted_data()
        self.error = error

    async def interpret(self, request):
        if self.error:
            raise self.error
        return RecruiterInterpretation.model_validate(self.data)


class RecordingWorkflow:
    def __init__(self, error=None):
        self.requests = []
        self.error = error

    async def generate(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return successful_response()


def test_valid_message_calls_existing_jd_contract():
    workflow = RecordingWorkflow()
    service = RecruiterChatService(FakeInterpreter(), workflow_factory=lambda: workflow)
    result = asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE)))
    assert result.status == "jd_generated"
    assert len(workflow.requests) == 1
    assert workflow.requests[0].required_skills == ["Python", "FastAPI"]
    assert result.job_description_result == successful_response()
    assert result.job_description_result.status == "draft"
    assert result.job_description_result.human_review_required is True


@pytest.mark.parametrize("field", ["responsibilities", "required_skills", "job_title", "role_summary"])
def test_missing_information_never_constructs_workflow(field):
    data = extracted_data()
    data["requirements"][field] = [] if field in {"responsibilities", "required_skills"} else None

    def forbidden_workflow():
        pytest.fail("Clarification must not construct the JD workflow.")

    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=forbidden_workflow)
    result = asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE)))
    assert result.status == "clarification"
    assert result.missing_fields == [field]


def test_unsupported_intent_does_not_run_jd():
    service = RecruiterChatService(FakeInterpreter({"intent": "unsupported", "requirements": None}),
        workflow_factory=lambda: pytest.fail("Unsupported request must not run JD."))
    result = asyncio.run(service.respond(RecruiterChatRequest(message="Publish this job to Discord.")))
    assert result.status == "unsupported"
    assert "not available" in result.assistant_message


def test_invented_required_skills_produce_clarification():
    data = extracted_data()
    data["requirements"]["required_skills"] = [evidence("Rust")]
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Invented facts must not generate."))
    result = asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE)))
    assert result.missing_fields == ["required_skills"]


def test_optional_invented_values_require_clarification():
    data = extracted_data()
    data["requirements"].update(location=evidence("Paris"), preferred_skills=[evidence("Rust")], minimum_experience_years=evidence(5, "5 years experience"))
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Unsupported optional facts must clarify."))
    result = asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE)))
    assert result.status == "clarification"
    assert set(result.missing_fields) == {"location", "preferred_skills", "minimum_experience_years"}


def test_explicit_optional_enums_are_preserved():
    data = extracted_data()
    data["requirements"].update(work_arrangement=evidence("remote"), employment_type=evidence("full_time", "full-time"))
    workflow = RecordingWorkflow()
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow)
    asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " A full-time remote role.")))
    assert workflow.requests[0].work_arrangement == "remote"
    assert workflow.requests[0].employment_type == "full_time"


def test_existing_cross_field_validation_cannot_be_bypassed():
    data = extracted_data()
    data["requirements"]["preferred_skills"] = [evidence("Python")]
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Invalid JD must not run."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE))).status == "clarification"


@pytest.mark.parametrize("value", ["", "   ", "x" * 4001, "unsafe\x00", "unsafe\x1b", "unsafe\u202e", "candidate CV details", "person@example.invalid"])
def test_invalid_chat_message(value):
    with pytest.raises(ValidationError):
        RecruiterChatRequest(message=value)


def test_extra_request_configuration_rejected():
    with pytest.raises(ValidationError):
        RecruiterChatRequest(message=MESSAGE, provider="other", api_key="synthetic")


def adapter(content=None, error=None, captured=None):
    capture = captured if captured is not None else {}
    return GroqRecruiterInstructionInterpreter(configured_settings(), client_factory=lambda **kwargs:
        FakeGroqClient(FakeCompletions(capture, content=content, error=error)))


def test_interpreter_strict_schema_and_safe_prompt():
    captured = {}
    result = asyncio.run(adapter(json.dumps(extracted_data()), captured=captured).interpret(RecruiterChatRequest(message=MESSAGE)))
    assert result.intent == "create_job_description"
    spec = captured["response_format"]["json_schema"]
    assert spec["strict"] is True
    for node in [spec["schema"], *spec["schema"]["$defs"].values()]:
        assert node["additionalProperties"] is False
        assert set(node["properties"]) == set(node["required"])
    assert "UNTRUSTED DATA" in captured["messages"][0]["content"]
    assert MESSAGE not in captured["messages"][0]["content"]
    assert "private-test-groq-key" not in json.dumps(captured)


@pytest.mark.parametrize("content", ["not-json", "{}", json.dumps({"intent": "publish_job", "requirements": None})])
def test_malformed_provider_output_fails_safely(content):
    with pytest.raises(GenerationProviderError) as error:
        asyncio.run(adapter(content).interpret(RecruiterChatRequest(message=MESSAGE)))
    assert content not in str(error.value)


def test_interpreter_timeout_sanitized():
    with pytest.raises(GenerationTimeoutError):
        asyncio.run(adapter(error=APITimeoutError(httpx.Request("POST", "https://example.invalid"))).interpret(RecruiterChatRequest(message=MESSAGE)))


async def send(data):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        return await client.post("/api/v1/recruiter-chat", json=data)


@pytest.mark.parametrize("error,http_status", [
    (MissingGenerationConfigurationError("PRIVATE_KEY"), 503),
    (GenerationTimeoutError("PRIVATE_TIMEOUT"), 504),
    (GenerationProviderError("PRIVATE_PROVIDER"), 502),
    (PolicyRetrievalError("PRIVATE_POLICY_DATABASE_URL"), 502),
    (RuntimeError("PRIVATE_INTERNAL_PATH"), 502),
])
def test_api_errors_are_sanitized(monkeypatch, error, http_status):
    monkeypatch.setattr(route, "get_recruiter_interpreter", lambda: FakeInterpreter(error=error))
    response = asyncio.run(send({"message": MESSAGE}))
    assert response.status_code == http_status
    assert "PRIVATE" not in response.text


def test_api_validation_does_not_echo_message(monkeypatch):
    monkeypatch.setattr(route, "get_recruiter_interpreter", lambda: pytest.fail("Invalid input must not interpret."))
    response = asyncio.run(send({"message": "PRIVATE_RECRUITER_TEXT\x00"}))
    assert response.status_code == 422
    assert "PRIVATE_RECRUITER_TEXT" not in response.text


def test_api_calls_actual_existing_graph_with_fake_external_boundaries(monkeypatch):
    from app.services import recruiter_chat as service_module
    context = policy_context()
    calls = []

    class Retriever:
        retrieval_mode = "semantic_bge_pgvector"

        async def retrieve(self, request):
            calls.append("retrieve")
            return context

    class Generator:
        async def generate(self, request, chunks):
            calls.append("generate")
            response = successful_response()
            draft = response.job_description.model_copy(update={"policy_citation_ids": [chunks[0].chunk.metadata.citation_id]})
            return JobDescriptionGenerationResult(draft=draft, model=response.model)

    workflow = JobDescriptionWorkflow(Retriever(), Generator())
    monkeypatch.setattr(route, "get_recruiter_interpreter", lambda: FakeInterpreter())
    original_service = service_module.RecruiterChatService
    monkeypatch.setattr(route, "RecruiterChatService", lambda interpreter:
        original_service(interpreter, workflow_factory=lambda: workflow))
    response = asyncio.run(send({"message": MESSAGE}))
    assert response.status_code == 200
    result = response.json()["job_description_result"]
    assert result["status"] == "draft"
    assert result["human_review_required"] is True
    assert result["grounding_citations"][0]["citation_id"] == context[0].chunk.metadata.citation_id
    assert calls == ["retrieve", "generate"]


def test_generation_orchestration_has_no_mcp_or_publishing_dependency():
    import ast
    from pathlib import Path

    for relative in ["services/recruiter_chat.py", "integrations/llm/recruiter_chat.py"]:
        tree = ast.parse((Path(__file__).parents[1] / "app" / relative).read_text(encoding="utf-8"))
        imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
        assert not any("mcp" in module or "publish" in module for module in imports)


@pytest.mark.parametrize("clause", ["Do not require Java.", "No Java required.", "Java is not required.", "Without Java.", "Don't require Java.", "Java isn't required."])
def test_negated_skill_clarifies_without_workflow(clause):
    data = extracted_data()
    data["requirements"]["required_skills"].append(evidence("Java"))
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Negation must clarify."))
    result = asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " " + clause)))
    assert result.missing_fields == ["required_skills"]


@pytest.mark.parametrize("field,value", [("required_skills", "Rust"), ("responsibilities", "Manage budgets")])
def test_one_unsupported_list_item_never_silently_disappears(field, value):
    data = extracted_data()
    data["requirements"][field].append(evidence(value))
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Partial extraction must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE))).missing_fields == [field]


def test_punctuation_and_role_purpose_source_clause():
    message = "Create a Backend Engineer JD for a team building FastAPI services. Responsibilities: Develop APIs; Write tests. Required skills: Python and FastAPI."
    data = extracted_data()
    data["requirements"]["role_summary"] = evidence("for a team building FastAPI services")
    data["requirements"]["responsibilities"][0] = evidence("Develop APIs.", "Develop APIs")
    workflow = RecordingWorkflow()
    result = asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=message)))
    assert result.status == "jd_generated"
    assert workflow.requests[0].role_summary == "for a team building FastAPI services"
    assert workflow.requests[0].responsibilities == ["Develop APIs", "Write tests"]


@pytest.mark.parametrize("clause", ["Our company started 5 years ago; no minimum experience requirement.", "The product roadmap spans 5 years.", "5 years of experience or 7 years of experience."])
def test_unrelated_or_ambiguous_years_clarify(clause):
    data = extracted_data()
    data["requirements"]["minimum_experience_years"] = evidence(5, clause)
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Unrelated years must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " " + clause))).missing_fields == ["minimum_experience_years"]


@pytest.mark.parametrize("clause", ["3 years of experience", "3+ years experience", "at least 3 years of backend experience"])
def test_experience_requires_explicit_context(clause):
    data = extracted_data()
    data["requirements"]["minimum_experience_years"] = evidence(3, clause)
    workflow = RecordingWorkflow()
    result = asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=MESSAGE + " " + clause)))
    assert result.status == "jd_generated"
    assert workflow.requests[0].minimum_experience_years == 3


@pytest.mark.parametrize("field,phrase,canonical", [
    ("employment_type", "full time", "full_time"), ("employment_type", "full-time", "full_time"),
    ("employment_type", "fulltime", "full_time"), ("work_arrangement", "work from home", "remote"),
    ("work_arrangement", "wfh", "remote"), ("work_arrangement", "on-site", "on_site"),
    ("work_arrangement", "on site", "on_site"), ("work_arrangement", "onsite", "on_site"),
    ("work_arrangement", "hybrid", "hybrid"),
])
def test_deterministic_enum_normalization(field, phrase, canonical):
    data = extracted_data()
    data["requirements"][field] = evidence(canonical, phrase)
    workflow = RecordingWorkflow()
    result = asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=MESSAGE + " " + phrase)))
    assert result.status == "jd_generated"
    assert getattr(workflow.requests[0], field) == canonical


@pytest.mark.parametrize("phrase", ["flexible", "remote or on-site"])
def test_unknown_or_ambiguous_enum_clarifies(phrase):
    data = extracted_data()
    data["requirements"]["work_arrangement"] = evidence("remote", phrase)
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Ambiguous enum must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " " + phrase))).missing_fields == ["work_arrangement"]


@pytest.mark.parametrize("message", ["Create a JD.\nSkills: Python\tFastAPI", "Create a JD.\r\nPython >= 3.11", "Create a transcript-processing engineer role", "Build resume-processing services", "Build candidate CV processing services", "Implement < and > comparisons", "<script>ordinary untrusted text</script>"])
def test_legitimate_multiline_and_technical_text(message):
    assert RecruiterChatRequest(message=message).message


@pytest.mark.parametrize("message", ["Email person@example.invalid", "Call +1 (202) 555-0199", "candidate John Doe", "Candidate John Doe", "applicant John Doe", "Here is a candidate CV", "John Doe's CV", "the candidate's CV", "the applicant's resume", "Upload this candidate CV", "Submit their resume", "Share the applicant resume"])
def test_obvious_candidate_data_rejected(message):
    with pytest.raises(ValidationError):
        RecruiterChatRequest(message=message)


def test_unicode_and_whitespace_evidence_normalization():
    data = extracted_data()
    data["requirements"]["job_title"] = evidence("Backend Engineer", "BACKEND   Engineer")
    workflow = RecordingWorkflow()
    assert asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=MESSAGE))).status == "jd_generated"


@pytest.mark.parametrize("error,status", [(PolicyRetrievalError("PRIVATE_PATH"), 502), (GenerationProviderError("PRIVATE_PROVIDER"), 502), (GenerationTimeoutError("PRIVATE_TIMEOUT"), 504), (MissingGenerationConfigurationError("PRIVATE_CONFIG"), 503)])
def test_workflow_failures_sanitized(monkeypatch, error, status):
    monkeypatch.setattr(route, "get_recruiter_interpreter", lambda: FakeInterpreter())
    original = RecruiterChatService
    monkeypatch.setattr(route, "RecruiterChatService", lambda interpreter: original(interpreter, workflow_factory=lambda: RecordingWorkflow(error)))
    response = asyncio.run(send({"message": MESSAGE}))
    assert response.status_code == status
    assert "PRIVATE" not in response.text


def test_generation_and_clarification_have_no_publication_side_effects(monkeypatch):
    import socket
    import subprocess
    import sys
    import types
    class ForbiddenMCP(types.ModuleType):
        def __getattr__(self, name):
            pytest.fail("Chat must not access MCP clients or publishers.")
    monkeypatch.setitem(sys.modules, "mcp", ForbiddenMCP("mcp"))
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: pytest.fail("Chat must not spawn a stdio publisher."))
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("No external publication connection."))
    workflow = RecordingWorkflow()
    service = RecruiterChatService(FakeInterpreter(), workflow_factory=lambda: workflow)
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE))).status == "jd_generated"
    assert len(workflow.requests) == 1
    data = extracted_data()
    data["requirements"]["required_skills"].append(evidence("Rust"))
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Clarification must stop."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE))).status == "clarification"


@pytest.mark.parametrize("field", ["job_title", "role_summary"])
def test_unsupported_required_scalar_evidence_clarifies(field):
    data = extracted_data()
    data["requirements"][field]["evidence"] = "invented source passage"
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Evidence must be copied."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE))).missing_fields == [field]


def test_conflicting_positive_negative_skill_occurrences_clarify():
    data = extracted_data()
    data["requirements"]["required_skills"].append(evidence("Java"))
    message = MESSAGE + " Require Java. Java is not required."
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Conflicting evidence must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=message))).missing_fields == ["required_skills"]


def test_preferred_skill_can_be_explicitly_optional():
    data = extracted_data()
    data["requirements"]["preferred_skills"] = [evidence("Rust", "Rust is optional")]
    workflow = RecordingWorkflow()
    assert asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=MESSAGE + " Rust is optional."))).status == "jd_generated"
    assert workflow.requests[0].preferred_skills == ["Rust"]


def test_multiline_evidence_is_normalized_before_existing_jd_validation():
    data = extracted_data()
    data["requirements"]["role_summary"] = evidence("Build and maintain\nsecure backend services.")
    workflow = RecordingWorkflow()
    assert asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=MESSAGE))).status == "jd_generated"
    assert workflow.requests[0].role_summary == "Build and maintain secure backend services"


@pytest.mark.parametrize("clause,value", [("3.5 years of experience", 5), ("3 to 5 years of experience", 5), ("3-5 years of experience", 5)])
def test_ambiguous_experience_quantity_clarifies(clause, value):
    data = extracted_data()
    data["requirements"]["minimum_experience_years"] = evidence(value, clause)
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Do not infer experience quantities."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " " + clause))).missing_fields == ["minimum_experience_years"]


REALISTIC_MESSAGE = "Create a Backend AI Engineer job description for a team building FastAPI services and reliable AI-backed backend systems. Responsibilities include building REST APIs, writing automated tests, and working with PostgreSQL. Required skills are Python, FastAPI, PostgreSQL, and Docker. This is a full-time remote role requiring at least 3 years of backend development experience."


def realistic_extraction():
    data = extracted_data()
    data["requirements"].update(
        job_title=evidence("Backend AI Engineer"),
        role_summary=evidence("Build FastAPI services and reliable AI-backed backend systems.", "for a team building FastAPI services and reliable AI-backed backend systems"),
        responsibilities=[evidence("Build REST APIs", "building REST APIs"), evidence("Write automated tests", "writing automated tests"), evidence("Work with PostgreSQL", "working with PostgreSQL")],
        required_skills=[evidence(skill) for skill in ["Python", "FastAPI", "PostgreSQL", "Docker"]],
        employment_type=evidence("full_time", "full-time"),
        work_arrangement=evidence("remote"),
        minimum_experience_years=evidence(3, "at least 3 years of backend development experience"),
    )
    return data


def test_exact_realistic_request_with_source_backed_imperative_values():
    workflow = RecordingWorkflow()
    result = asyncio.run(RecruiterChatService(FakeInterpreter(realistic_extraction()), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=REALISTIC_MESSAGE)))
    assert result.status == "jd_generated"
    assert result.job_description_result.status == "draft"
    assert result.job_description_result.human_review_required is True
    assert len(workflow.requests) == 1
    request = workflow.requests[0]
    assert request.job_title == "Backend AI Engineer"
    assert request.role_summary == "Build FastAPI services and reliable AI-backed backend systems"
    assert request.responsibilities == ["Build REST APIs", "Write automated tests", "Work with PostgreSQL"]
    assert request.required_skills == ["Python", "FastAPI", "PostgreSQL", "Docker"]
    assert request.employment_type == "full_time"
    assert request.work_arrangement == "remote"
    assert request.minimum_experience_years == 3


@pytest.mark.parametrize("value", ["Build GraphQL APIs", "Design REST APIs", "Build REST APIs and manage budgets"])
def test_normalization_does_not_accept_arbitrary_paraphrases_or_added_facts(value):
    data = realistic_extraction()
    data["requirements"]["responsibilities"][0] = evidence(value, "building REST APIs")
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Unsupported normalization must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=REALISTIC_MESSAGE))).missing_fields == ["responsibilities"]


def test_normalized_value_still_requires_copied_evidence():
    data = realistic_extraction()
    data["requirements"]["responsibilities"][0] = evidence("Build REST APIs", "building REST APIs securely")
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Invented evidence must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=REALISTIC_MESSAGE))).missing_fields == ["responsibilities"]


def test_normalization_does_not_bypass_negation():
    data = extracted_data()
    data["requirements"]["responsibilities"].append(evidence("Build Java services", "building Java services"))
    service = RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: pytest.fail("Negated source must clarify."))
    assert asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " Do not require building Java services."))).missing_fields == ["responsibilities"]


@pytest.mark.parametrize("message", ["Publish this job to Discord.", "Post this JD on LinkedIn.", "Can you post the draft to Discord?", "I want to publish this JD on Discord.", "Create a JD and then publish it to LinkedIn."])
def test_posting_requests_are_unavailable_without_external_calls(monkeypatch, message):
    monkeypatch.setattr(route, "get_recruiter_interpreter", lambda: FakeInterpreter(error=AssertionError("Posting must not call Groq.")))
    response = asyncio.run(send({"message": message}))
    assert response.status_code == 200
    assert response.json() == {
        "status": "unsupported", "intent": "unsupported",
        "assistant_message": "Job posting by chat instruction is not available. Review a draft and use its Publish to Discord button.",
    }


def test_posting_word_in_job_responsibility_does_not_block_drafting():
    workflow = RecordingWorkflow()
    service = RecruiterChatService(FakeInterpreter(), workflow_factory=lambda: workflow)
    result = asyncio.run(service.respond(RecruiterChatRequest(message=MESSAGE + " Responsibilities include posting job adverts.")))
    assert result.status == "jd_generated"


def test_validated_optional_context_is_returned_for_publication_mapping():
    data = realistic_extraction()
    data["requirements"]["location"] = evidence("Dhaka")
    workflow = RecordingWorkflow()
    result = asyncio.run(RecruiterChatService(FakeInterpreter(data), workflow_factory=lambda: workflow).respond(RecruiterChatRequest(message=REALISTIC_MESSAGE + " Location: Dhaka.")))
    assert result.publishing_context.model_dump() == {"location": "Dhaka", "employment_type": "full_time", "work_arrangement": "remote"}
