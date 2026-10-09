"""Only concrete approved synthetic-policy practices become preferred suggestions."""
from uuid import uuid4

import pytest

from app.rag.chunking import chunk_company_policy
from app.rag.retrieval import load_demo_company_policy_source, RetrievedPolicyChunk, WhitespaceTokenCounter
from app.rag.screening_policy import policy_screening_suggestions
from app.schemas.job_description import JobDescriptionGenerationRequest
from app.schemas.recruiter_chat import RecruiterChatRequest
from app.services.recruiter_chat import RecruiterChatService
from test_recruiter_chat import FakeInterpreter, RecordingWorkflow, MESSAGE


def request(summary="Build secure backend services."):
    return JobDescriptionGenerationRequest(job_title="Synthetic Engineer", role_summary=summary,
        responsibilities=["Develop APIs"], required_skills=["Python"], minimum_experience_years=0)


def context(source=None):
    source = source or load_demo_company_policy_source()
    return tuple(RetrievedPolicyChunk(chunk=chunk, source=source.source_metadata())
                 for chunk in chunk_company_policy(source, WhitespaceTokenCounter()))


def test_only_concrete_preferred_practices_with_exact_source_evidence():
    chunks = context()
    result = policy_screening_suggestions(request(), chunks)
    assert [item.description for item in result] == ["Applying access controls", "Reporting security incidents"]
    assert all(item.is_hard is False and item.category == "skill" for item in result)
    for item in result:
        chunk = next(c for c in chunks if c.chunk.metadata.citation_id == item.citation_id)
        assert item.evidence in chunk.chunk.text
        assert item.source_title == "Synthetic Demo Company Policy"
    assert policy_screening_suggestions(request("Write technical documentation."), chunks) == []
    assert policy_screening_suggestions(request(), ()) == []


@pytest.mark.parametrize("changes", [
    {"source_id": uuid4()}, {"source_version": "unapproved-v2"},
    {"text": "# Data Protection and Privacy Expectations\nDo not require following access controls or reporting incidents."},
])
def test_identity_version_and_exact_approved_content_are_required(changes):
    source = load_demo_company_policy_source().model_copy(update=changes)
    assert policy_screening_suggestions(request(), context(source)) == []


def test_chat_preserves_policy_provenance_and_never_auto_confirms():
    import asyncio
    workflow = RecordingWorkflow()
    from test_job_descriptions_endpoint import successful_response
    draft = successful_response().model_copy(update={"policy_screening_suggestions": policy_screening_suggestions(request(), context())})
    async def generate(*args, **kwargs): return draft
    workflow.generate = generate
    result = asyncio.run(RecruiterChatService(FakeInterpreter(), workflow_factory=lambda: workflow).respond(
        RecruiterChatRequest(message=MESSAGE)))
    policy_criteria = [c for c in result.screening_suggestions.criteria if c.criterion_id.startswith("policy-")]
    assert len(policy_criteria) == 2 and all(not c.is_hard for c in policy_criteria)
    sources = [s for s in result.screening_suggestion_sources if s.source == "company_policy"]
    assert {s.criterion_id for s in sources} == {c.criterion_id for c in policy_criteria}
    assert all(s.citation_id and s.source_title and s.evidence for s in sources)
