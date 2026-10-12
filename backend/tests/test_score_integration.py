"""Actual auth/routes/graph; transactional SQL double and synthetic profiles only."""
import asyncio
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config

from app.api.routers import screening as route
from app.agents.screening.workflow import CandidateScreeningWorkflow
from app.db.models.recruiter import CandidateScoreRecord
from app.services.batch_screening import BatchScreeningService
from test_batch_screening import Profiles, candidate, snapshot
from test_screening_matching import FakeMatcher, semantic_result
from test_recruiter_records import workspace, client, login, TABLES


def test_owned_scoring_approval_persistence_reload_and_revision(monkeypatch, workspace):
    db, users, password = workspace
    monkeypatch.setitem(TABLES, "candidate_scores", CandidateScoreRecord)
    profiles = [candidate(), candidate(skills=("Java",)), candidate("parsing_failed")]
    service = BatchScreeningService(Profiles(profiles), CandidateScreeningWorkflow(FakeMatcher([semantic_result("python", "not_found", evidence=[])])))
    monkeypatch.setattr(route, "BatchScreeningService", lambda **kwargs: service)

    async def scenario():
        async with client() as owner, client() as foreign:
            await login(owner, users[0], password)
            await login(foreign, users[1], password)
            job = (await owner.post("/api/v1/jobs", json={"job_title": "Synthetic engineer"})).json()
            identifier, reference, batch_id = job["id"], job["job_reference"], str(uuid4())
            criteria = snapshot()["criteria"]
            approved = {"revision": 1, "criteria": criteria, "confirmed": True,
                "weights": {"skill": 100, "experience": 0, "education": 0}}
            assert (await owner.put(f"/api/v1/jobs/{identifier}/criteria", json={**approved, "weights": {"skill": 99, "experience": 0, "education": 0}})).status_code == 422
            assert (await owner.put(f"/api/v1/jobs/{identifier}/criteria", json={**approved, "score": 100})).status_code == 422
            saved = await owner.put(f"/api/v1/jobs/{identifier}/criteria", json=approved)
            assert saved.status_code == 200 and saved.json()["scoring_weights"]["skill"] == 100
            reviewed = snapshot(job_reference=reference, job_title="Synthetic engineer")
            endpoint = f"/api/v1/cv-uploads/{reference}/{batch_id}/screen"
            stale = await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "1"}, json=reviewed)
            assert stale.status_code == 409 and not profiles[0].upload_id in [r.upload_id for r in db.get(CandidateScoreRecord, [])]
            response = await owner.post(endpoint, headers={"X-TalentTrace-Job-Revision": "2"}, json=reviewed)
            assert response.status_code == 200
            body = response.json(); scoring = body["scoring"]
            assert scoring["criteria_revision"] == 2 and scoring["scoring_version"] == "f2-coverage-v1"
            assert scoring["ranking"] == [{"upload_id": str(profiles[0].upload_id), "score": 100.0, "rank": 1, "tied": False}]
            scores = {c["upload_id"]: c for c in scoring["candidates"]}
            assert scores[str(profiles[0].upload_id)]["dimensions"][0]["matches"] == body["candidates"][0]["result"]["matching_result"]["matches"]
            assert scores[str(profiles[1].upload_id)]["score"] is None
            assert body["candidates"][1]["result"]["screening_decision"] == "excluded"
            assert scores[str(profiles[2].upload_id)]["reason"] == "screening_incomplete"
            assert len(db[CandidateScoreRecord]) == 3
            from app.services.score_records import restore_candidate_score
            from pydantic import ValidationError
            for row in db[CandidateScoreRecord]:
                try:
                    restore_candidate_score(row.payload)
                except ValidationError as error:
                    pytest.fail(str([(e["loc"], e["type"]) for e in error.errors(include_input=False)]))
            read_url = f"/api/v1/jobs/{identifier}/batches/{batch_id}/scores"
            assert (await foreign.get(read_url)).status_code == 404
            assert (await foreign.post(endpoint, json=reviewed)).status_code == 404
            restored = await owner.get(read_url)
            assert restored.status_code == 200 and restored.json()["ranking"] == scoring["ranking"]
            db[CandidateScoreRecord][0].score = 101
            invalid = await owner.get(read_url)
            assert invalid.status_code == 500 and invalid.json() == {"detail": "Saved scores could not be validated."}
            assert (await owner.post(endpoint, json=reviewed)).status_code == 200
            assert len(db[CandidateScoreRecord]) == 3  # Atomic replacement, not duplicates.
            assert (await owner.put(f"/api/v1/jobs/{identifier}/criteria", json={**approved, "revision": 1})).status_code == 409
            assert (await owner.put(f"/api/v1/jobs/{identifier}/criteria", json={**approved, "revision": 2, "confirmed": False})).status_code == 200
            assert (await owner.get(read_url)).status_code == 409
            assert (await owner.post(endpoint, json=reviewed)).status_code == 409
            assert len(db[CandidateScoreRecord]) == 3  # Historical records remain.
    asyncio.run(scenario())


def test_score_ranking_ties_zero_and_non_scored_are_separate():
    from uuid import UUID
    from app.services.score_records import score_ranking, ScoringBatch
    from app.schemas.candidate_score import ScoringWeights
    from test_candidate_scoring import scored
    from pydantic import ValidationError
    weights = ScoringWeights(skill=100, experience=0, education=0)
    high, _, _ = scored(["supported"], weights=weights)
    tie = high.model_copy(update={"upload_id": UUID(int=2)})
    zero, _, _ = scored(["not_found"], weights=weights)
    zero = zero.model_copy(update={"upload_id": UUID(int=3)})
    excluded, _, _ = scored(["not_found"], hard=True, weights=weights)
    excluded = excluded.model_copy(update={"upload_id": UUID(int=4)})
    rows = [zero, tie, excluded, high]
    ranking = score_ranking(rows)
    assert [(r.rank, r.tied, r.score) for r in ranking] == [(1, True, 100), (1, True, 100), (3, False, 0)]
    assert score_ranking(list(reversed(rows))) == ranking
    batch = ScoringBatch(job_id=uuid4(), job_reference=high.job_reference, batch_id=uuid4(), criteria_revision=2,
        weights=weights, candidates=rows, ranking=ranking)
    with pytest.raises(ValidationError):
        ScoringBatch.model_validate({**batch.model_dump(), "ranking": []})


def test_scoring_migration_offline_only(capsys):
    from io import StringIO
    output = StringIO()
    configuration = Config("alembic.ini", stdout=output)
    configuration.attributes["output_buffer"] = output
    command.upgrade(configuration, "0002_recruiter_jobs:head", sql=True)
    sql = capsys.readouterr().out
    assert "CREATE TABLE candidate_scores" in sql and "uq_candidate_score_version" in sql
    assert "REFERENCES job_profiles" in sql and "ck_job_scoring_weights" in sql
    # Numeric JSON colons in TextClause used to become bind parameters, emitting
    # invalid defaults such as {"skill"NULL}. Require the actual safe DDL default.
    assert "DEFAULT jsonb_build_object('skill', 50, 'experience', 30, 'education', 20) NOT NULL" in sql
    assert "DROP TABLE" not in sql
    output = StringIO(); configuration.attributes["output_buffer"] = output
    command.downgrade(configuration, "head:0002_recruiter_jobs", sql=True)
    sql = capsys.readouterr().out
    assert "DROP TABLE candidate_scores" in sql
    assert "DROP TABLE job_profiles" not in sql
