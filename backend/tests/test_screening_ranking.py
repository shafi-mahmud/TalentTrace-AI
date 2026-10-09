"""Synthetic ranking over actual screening decisions; no live providers."""
from uuid import UUID, uuid4

import httpx
import pytest
from pydantic import ValidationError

from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.api.routers import screening as route
from app.schemas.batch_screening import BatchScreeningResponse, ReviewedJobSnapshot
from app.services.batch_screening import BatchScreeningService
from app.services.screening_ranking import rank_eligible_candidates
from test_batch_screening import Profiles, REFERENCE, candidate, post, snapshot
from test_screening_decisions import scenario, screen
from test_screening_matching import FakeMatcher, attribute, fact_refs, request, semantic_result
from app.services.screening_matching import qualification_facts


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        pytest.fail("Ranking tests must not call providers.")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden)


def decision(statuses, number, hard=False):
    supplied, matcher = scenario(tuple((f"skill-{i}", status, hard) for i, status in enumerate(statuses)))
    supplied = supplied.model_copy(update={"upload_id": UUID(int=number)})
    return screen(supplied, matcher), supplied.criteria


def rank(results, criteria):
    return rank_eligible_candidates(results, job_reference=REFERENCE, criteria=criteria)


def test_ordering_ties_repeatability_and_zero_support():
    a, criteria = decision(["supported", "not_found"], 4)
    b, _ = decision(["supported", "supported"], 3)
    c, _ = decision(["supported", "supported"], 2)
    d, _ = decision(["ambiguous", "not_found"], 1)
    rows = rank([a, b, d, c], criteria)
    assert [r["upload_id"].int for r in rows] == [2, 3, 4, 1]
    assert [r["rank"] for r in rows] == [1, 1, 3, 4]
    assert [r["tied"] for r in rows] == [True, True, False, False]
    assert [r["supported_count"] for r in rows] == [2, 2, 1, 0]
    assert rows[-1]["ambiguous_count"] == rows[-1]["not_found_count"] == 1
    assert rank([d, c, b, a], criteria) == rows
    assert set(rows[0]) == {"upload_id", "rank", "tied", "supported_count", "ambiguous_count", "not_found_count", "total_requirements"}


def test_semantic_and_deterministic_support_count_equally_preserve_evidence():
    supplied, _ = scenario((("skill-0", "supported", False),))
    exact = screen(supplied, FakeMatcher(error=AssertionError("No call")))
    semantic_input = supplied.model_copy(update={"upload_id": uuid4(), "qualifications": request(skills=("Django",)).qualifications})
    facts = qualification_facts(semantic_input)
    semantic = screen(semantic_input, FakeMatcher([semantic_result("skill-0", evidence=fact_refs((facts[0],)))]))
    before = semantic.model_dump()
    rows = rank([exact, semantic], supplied.criteria)
    assert all(r["rank"] == 1 and r["tied"] and r["supported_count"] == 1 for r in rows)
    assert exact.matching_result.matches[0].match_method == "deterministic"
    assert semantic.matching_result.matches[0].match_method == "semantic"
    assert semantic.model_dump() == before


def test_all_zero_support_candidates_share_rank_without_conflating_evidence():
    a, criteria = decision(["ambiguous"], 2)
    b, _ = decision(["not_found"], 1)
    rows = rank([a, b], criteria)
    assert [r["upload_id"].int for r in rows] == [1, 2]
    assert all(r["rank"] == 1 and r["tied"] and r["supported_count"] == 0 for r in rows)
    assert rows[0]["not_found_count"] == 1 and rows[1]["ambiguous_count"] == 1


@pytest.mark.parametrize("status", ["not_found", "ambiguous"])
def test_hard_exclusions_and_uncertainty_never_rank(status):
    result, criteria = decision([status], 1, hard=True)
    assert rank([result], criteria) == []
    assert result.screening_decision == ("excluded" if status == "not_found" else "insufficient_evidence")


@pytest.mark.parametrize("status", ["source_unavailable", "parsing_failed", "provider"])
def test_operational_failures_are_not_ranked_or_excluded(status):
    supplied = request(status=status if status != "provider" else "parsed", skills=("Unrelated",))
    result = screen(supplied, FakeMatcher(error=RuntimeError("Synthetic provider failure")))
    assert rank([result], supplied.criteria) == []
    assert result.screening_decision is None


@pytest.mark.parametrize("change", ["job", "category", "hard", "duplicate"])
def test_ranking_rejects_mixed_snapshots_and_duplicate_uploads(change):
    result, criteria = decision(["supported"], 1)
    results = [result]
    reference = REFERENCE
    if change == "job": reference = "TT-JOB-FFFFFFFFFFFFFFFF"
    if change == "category": criteria = (criteria[0].model_copy(update={"category": "education"}),)
    if change == "hard": criteria = (criteria[0].model_copy(update={"is_hard": True}),)
    if change == "duplicate": results += [result]
    with pytest.raises(ValueError):
        rank_eligible_candidates(results, job_reference=reference, criteria=criteria)


def test_api_ranking_is_contact_independent_and_preserves_batch_scope(monkeypatch):
    profiles = [candidate(), candidate(), candidate("parsing_failed")]
    service = BatchScreeningService(Profiles(profiles), CandidateScreeningWorkflow(FakeMatcher(error=AssertionError("No call"))))
    monkeypatch.setattr(route, "BatchScreeningService", lambda **kwargs: service)
    batch_id = uuid4()
    first = post(batch_id=batch_id)
    assert first.status_code == 200
    body = first.json()
    assert body["batch_id"] == str(batch_id) and body["snapshot"] == snapshot()
    assert len(body["ranking"]) == 2
    assert all(r["rank"] == 1 and r["tied"] for r in body["ranking"])
    assert body["candidates"][2]["result"]["status"] == "source_unavailable"
    profiles[0] = profiles[0].model_copy(update={"contact": profiles[0].contact.model_copy(update={
        "candidate_name": attribute("Synthetic Person"), "emails": [attribute("synthetic@example.invalid")],
        "location": attribute("Synthetic City")})})
    second = post(batch_id=batch_id)
    assert second.status_code == 200 and second.json()["ranking"] == body["ranking"]
    assert "Synthetic Person" not in second.text


@pytest.mark.parametrize("change", ["count", "rank", "tie", "omit", "extra", "identity", "fraction", "boolean"])
def test_response_rejects_invented_or_incomplete_ranking(change):
    result, criteria = decision(["supported"], 1)
    reviewed = ReviewedJobSnapshot(job_reference=REFERENCE, job_title="Synthetic role", criteria_confirmed=True, criteria=list(criteria))
    payload = dict(job_reference=REFERENCE, batch_id=uuid4(), snapshot=reviewed, processed_count=1,
                   candidates=[dict(upload_id=result.upload_id, result=result, error_code=None, overall_coverage="met")], ranking=rank([result], criteria))
    row = payload["ranking"][0]
    if change == "count": row.update(supported_count=0, not_found_count=1)
    if change == "rank": row["rank"] = 2
    if change == "tie": row["tied"] = True
    if change == "omit": payload["ranking"] = []
    if change == "extra": row["score"] = 100
    if change == "identity": row["upload_id"] = uuid4()
    if change == "fraction": row["rank"] = 1.5
    if change == "boolean": row["supported_count"] = True
    with pytest.raises(ValidationError): BatchScreeningResponse(**payload)
