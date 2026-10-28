"""20 fictional applications through real auth, graph, scoring and reload services.

Profile extraction/semantic interpretation and SQL execution are deterministic
test doubles. This is not a provider accuracy or throughput benchmark.
"""
import asyncio
from collections import Counter
from uuid import UUID, uuid4

import httpx
import pytest

from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.api.routers import screening as route
from app.db.models.recruiter import CandidateScoreRecord
from app.schemas.candidate_profile import CandidateContact, CandidateEducation, CandidateProfile
from app.schemas.candidate_score import ScoringWeights
from app.schemas.screening import SemanticMatchingResponse
from app.services.batch_screening import BatchScreeningService
from app.services.candidate_scoring import score_candidate
from app.core.config import settings
from app.integrations.llm import screening_selection
from pydantic import SecretStr
from test_batch_screening import Profiles
from test_recruiter_records import TABLES, client, login, workspace
from test_screening_matching import attribute, request


CRITERIA = [
    dict(criterion_id="python", description="Python", category="skill", is_hard=True),
    dict(criterion_id="sql", description="SQL", category="skill", is_hard=False),
    dict(criterion_id="experience", description="Minimum 2 years of relevant experience",
         category="experience", is_hard=False),
    dict(criterion_id="education", description="Bachelor of Science in Computer Science",
         category="education", is_hard=False),
]
PRIVATE_MARKER = "private-contact@example.invalid"


@pytest.fixture(autouse=True)
def no_provider_transport(monkeypatch):
    async def denied(*args, **kwargs):
        pytest.fail("External provider transport must not be used")
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", denied)


def profiles():
    values = []
    for i in range(20):
        education = [] if i in (2, 3) else [CandidateEducation(
            institution=None, qualification=attribute(CRITERIA[3]["description"]),
            field_of_study=None, date_or_period=None)]
        supplied = request(skills=("Java" if 15 <= i < 19 else "Python",)
                           + (() if i in (2, 3) else ("SQL",)),
                           activities=(f"Synthetic evidence {i:02d}",), education=education)
        values.append(CandidateProfile(upload_id=UUID(int=i+1), parsing_status="parsed",
            qualifications=supplied.qualifications,
            contact=CandidateContact(candidate_name=attribute("Fictional private contact"),
                emails=[attribute(PRIVATE_MARKER)], phones=[], links=[], location=None)))
    return values


class Matcher:
    """Explicit semantic outcomes, not a replacement matching algorithm."""
    def __init__(self, fail_last=True):
        self.calls = 0
        self.fail_last = fail_last

    async def match(self, criteria, facts):
        self.calls += 1
        activity = next(f for f in facts if f.kind == "work_activity")
        index = int(activity.value.rsplit(" ", 1)[1])
        if index == 19 and self.fail_last:
            raise RuntimeError("Synthetic terminal provider failure")
        rows = []
        for criterion in criteria:
            status = ("ambiguous" if 4 <= index < 15 else
                      "not_found" if index == 3 else "supported") if criterion.category == "experience" else "not_found"
            rows.append(dict(criterion_id=criterion.criterion_id, match_status=status,
                evidence=[] if status == "not_found" else [dict(fact_id=activity.fact_id, value=activity.value)]))
        return SemanticMatchingResponse.model_validate({"results": rows})


def test_twenty_applications_auth_graph_scoring_reload_and_revision(monkeypatch, workspace):
    database, users, password = workspace
    monkeypatch.setitem(TABLES, "candidate_scores", CandidateScoreRecord)
    matcher = Matcher(fail_last=False)
    parsed = Profiles(profiles())
    service = BatchScreeningService(parsed, CandidateScreeningWorkflow(matcher))
    # Keep the current request-level provider/consent checks; double only the
    # extraction/matching service constructed behind that approved boundary.
    monkeypatch.setattr(settings, "groq_api_key", SecretStr("offline-synthetic-not-a-key"))
    monkeypatch.setattr(screening_selection, "BatchScreeningService", lambda **kwargs: service)

    async def scenario():
        async with client() as owner, client() as foreign:
            await login(owner, users[0], password)
            await login(foreign, users[1], password)
            job = (await owner.post("/api/v1/jobs", json={"job_title": "Synthetic acceptance"})).json()
            job_id, reference, batch = job["id"], job["job_reference"], str(uuid4())
            approval = dict(revision=1, criteria=CRITERIA, confirmed=True,
                weights=dict(skill=50, experience=30, education=20))
            assert (await owner.put(f"/api/v1/jobs/{job_id}/criteria", json=approval)).status_code == 200
            snapshot = dict(job_reference=reference, job_title="Synthetic acceptance",
                            criteria_confirmed=True, criteria=CRITERIA)
            endpoint = f"/api/v1/cv-uploads/{reference}/{batch}/screen"
            read = f"/api/v1/jobs/{job_id}/batches/{batch}/scores"
            assert (await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "1"}, json=snapshot)).status_code == 409
            assert (await foreign.post(endpoint, json=snapshot)).status_code == 404
            assert matcher.calls == 0 and not parsed.calls
            assert (await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "2"}, json=snapshot)).status_code == 422
            assert matcher.calls == 0 and not parsed.calls
            owner.headers.update({"X-TalentTrace-AI-Provider":"groq", "X-TalentTrace-External-Processing":"confirmed"})

            response = await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "2"}, json=snapshot)
            assert response.status_code == 200
            body = response.json()
            assert PRIVATE_MARKER not in response.text and "Fictional private contact" not in response.text
            assert body["processed_count"] == len(body["candidates"]) == 20
            assert len({c["upload_id"] for c in body["candidates"]}) == 20
            assert Counter(c["result"]["screening_decision"] for c in body["candidates"]) == {"eligible": 16, "excluded": 4}
            scoring = body["scoring"]
            assert Counter(c["reason"] for c in scoring["candidates"]) == {None: 5, "uncertain_evidence": 11, "not_eligible": 4}
            assert [c["score"] for c in scoring["candidates"][:4]] == [100, 100, 55, 25]
            assert all(c["score"] is None and c["dimensions"] == [] for c in scoring["candidates"][4:19])
            for item in body["candidates"][4:15]:
                experience = next(m for m in item["result"]["matching_result"]["matches"] if m["criterion_id"] == "experience")
                assert experience["match_status"] == "ambiguous" and experience["evidence"]
                assert experience["explanation"]  # Initial batch retains the uncertainty evidence.
            assert [(r["score"], r["rank"], r["tied"]) for r in scoring["ranking"]] == [(100, 1, True), (100, 1, True), (100, 1, True), (55, 4, False), (25, 5, False)]
            assert len(body["ranking"]) == 16  # Requirement coverage is not numeric-score ranking.
            assert "Synthetic terminal provider failure" not in response.text
            for candidate, score in zip(body["candidates"][:4], scoring["candidates"][:4]):
                matches = candidate["result"]["matching_result"]["matches"]
                assert {m["criterion_id"]: m for d in score["dimensions"] for m in d["matches"]} == {m["criterion_id"]: m for m in matches}
                assert all(m["explanation"] for m in matches)
            assert any(e["source"]["method"] == "ocr" for d in scoring["candidates"][0]["dimensions"] for m in d["matches"] for e in m["evidence"])

            # Real persistence/read services over independent transactional SQL doubles.
            assert len(database[CandidateScoreRecord]) == 20
            restored = await owner.get(read)
            assert restored.status_code == 200 and restored.json() == scoring
            assert PRIVATE_MARKER not in restored.text
            assert (await foreign.get(read)).status_code == 404
            other = (await owner.post("/api/v1/jobs", json={"job_title": "Other synthetic job"})).json()
            assert (await owner.put(f"/api/v1/jobs/{other['id']}/criteria", json=approval)).status_code == 200
            assert (await owner.get(f"/api/v1/jobs/{other['id']}/batches/{batch}/scores")).status_code == 404
            assert (await owner.get(f"/api/v1/jobs/{job_id}/batches/{uuid4()}/scores")).status_code == 404

            repeated = await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "2"}, json=snapshot)
            assert repeated.status_code == 200 and repeated.json() == body
            assert len(database[CandidateScoreRecord]) == 20  # Exact replacement, no duplicate outcomes.
            matcher.fail_last = True
            failed = await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "2"}, json=snapshot)
            assert failed.status_code == 200 and failed.json().get("scoring") is None
            assert Counter(c["result"]["screening_decision"] for c in failed.json()["candidates"]) == {"eligible":15,"excluded":4,None:1}
            assert (await owner.get(read)).json() == scoring  # Failed retry cannot replace saved evidence.
            assert len(database[CandidateScoreRecord]) == 20
            calls = matcher.calls
            assert (await owner.put(f"/api/v1/jobs/{job_id}/criteria", json={**approval, "revision": 2})).status_code == 200
            assert (await owner.get(read)).status_code == 404
            assert (await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "2"}, json=snapshot)).status_code == 409
            assert matcher.calls == calls and len(database[CandidateScoreRecord]) == 20
    asyncio.run(scenario())


def test_positive_weight_ambiguity_abstains_without_changing_eligibility():
    async def scenario():
        from app.schemas.batch_screening import ReviewedJobSnapshot
        snapshot = ReviewedJobSnapshot(job_reference="TT-JOB-0123456789ABCDEF",
            job_title="Synthetic acceptance", criteria_confirmed=True, criteria=CRITERIA)
        batch = await BatchScreeningService(Profiles(profiles()), CandidateScreeningWorkflow(Matcher())).screen_batch(
            snapshot.job_reference, UUID(int=100), snapshot)
        result = batch.candidates[4].result
        default = score_candidate(result, job_reference=snapshot.job_reference, criteria=snapshot.criteria)
        assert result.screening_decision == "eligible" and default.reason == "uncertain_evidence"
        explicit = score_candidate(result, job_reference=snapshot.job_reference, criteria=snapshot.criteria,
            weights=ScoringWeights(skill=80, experience=0, education=20))
        assert explicit.score == 100  # Only explicit zero weight ignores this dimension.
        assert default.score is None and result.matching_result.matches[2].match_status == "ambiguous"
    asyncio.run(scenario())
