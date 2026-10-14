"""Synthetic owner/selection integration; SQL double, no provider calls."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from alembic.config import Config
from alembic import command

from app.db.models.recruiter import CandidateScoreRecord, InterviewSchedule, JobProfile
from app.schemas.interview import InterviewRequest
from app.schemas.candidate_score import ScoringWeights
from test_candidate_scoring import scored
from test_recruiter_records import workspace, client, login, TABLES


def request(batch_id=None, upload_id=None, **changes):
    return {"batch_id":str(batch_id or uuid4()), "upload_id":str(upload_id or uuid4()),
        "criteria_revision":2, "selection_confirmed":True,
        "scheduled_at":(datetime.now(timezone.utc)+timedelta(days=2)).isoformat(),
        "timezone":"Asia/Dhaka", "duration_minutes":30, **changes}


@pytest.mark.parametrize("change", [{"timezone":"Not/AZone"}, {"timezone":"../private"},
    {"timezone":"x"*65}, {"duration_minutes":14}, {"duration_minutes":181}, {"duration_minutes":30.0},
    {"criteria_revision":True}, {"selection_confirmed":False}, {"selection_confirmed":1},
    {"confirm_eligible_unscored":"true"}, {"scheduled_at":"2026-10-20T10:00:00"},
    {"scheduled_at":1900000000}, {"score":100}, {"screening_decision":"eligible"}, {"meeting_url":"https://example.test"}])
def test_bounded_request(change):
    with pytest.raises(ValidationError):
        InterviewRequest.model_validate(request(**change))


def test_offset_is_normalized_to_utc():
    value=InterviewRequest.model_validate(request(scheduled_at="2026-11-20T15:00:00+06:00"))
    assert value.scheduled_at.hour == 9 and value.scheduled_at.utcoffset().total_seconds() == 0


def test_selection_owner_revision_duplicates_and_unscored_confirmation(monkeypatch,workspace):
    db,users,password=workspace
    monkeypatch.setitem(TABLES,"interview_schedules",InterviewSchedule)
    monkeypatch.setitem(TABLES,"candidate_scores",CandidateScoreRecord)
    weights=ScoringWeights(skill=100,experience=0,education=0)
    good,_,criteria=scored(["supported"],weights=weights)
    uncertain,_,_=scored(["ambiguous"],weights=weights)
    excluded,_,_=scored(["not_found"],hard=True,weights=weights)
    incomplete=good.model_copy(update={"status":"not_evaluated","reason":"screening_incomplete",
        "screening_decision":None,"score":None,"dimensions":()})
    job=JobProfile(id=uuid4(),recruiter_id=users[0].id,job_reference=good.job_reference,
        job_title="Synthetic job",revision=2,scoring_weights=weights.model_dump(),sources=[],suggestions={},confirmed_snapshot={"criteria":[]})
    db[JobProfile]=[job]; batch_id=uuid4();db[CandidateScoreRecord]=[]
    candidates=[]
    for score in (good,uncertain,excluded,incomplete):
        score=score.model_copy(update={"upload_id":uuid4()});candidates.append(score)
        db[CandidateScoreRecord].append(CandidateScoreRecord(id=uuid4(),job_id=job.id,batch_id=batch_id,
            upload_id=score.upload_id,criteria_revision=2,scoring_version="f2-coverage-v1",score=score.score,payload=score.model_dump(mode="json")))
    path=f"/api/v1/jobs/{job.id}/interviews"
    async def scenario():
        async with client() as owner,client() as foreign,client() as anonymous:
            assert (await anonymous.get(path)).status_code == 401
            await login(owner,users[0],password);await login(foreign,users[1],password)
            supplied=request(batch_id,candidates[0].upload_id)
            assert (await foreign.post(path,json=supplied)).status_code==404
            assert (await foreign.get(path)).status_code==404
            assert (await owner.post(path,json={**supplied,"criteria_revision":1})).status_code==409
            assert (await owner.post(path,json={**supplied,"scheduled_at":"2020-01-01T10:00:00Z"})).status_code==422
            assert (await owner.post(path,json={**supplied,"upload_id":str(uuid4())})).status_code==404
            assert (await owner.post(path,json={**supplied,"batch_id":str(uuid4())})).status_code==404
            for score in candidates[2:]:
                assert (await owner.post(path,json=request(batch_id,score.upload_id))).status_code==409
            initial=await owner.post(path,json=supplied)
            assert initial.status_code==201 and initial.json()["unscored_confirmed"] is False
            assert initial.json()["scheduled_at"].endswith("Z")
            assert "meeting_url" not in initial.json() and "recruiter_id" not in initial.json()
            assert (await owner.post(path,json=supplied)).status_code==409
            uncertain=request(batch_id,candidates[1].upload_id,scheduled_at=(datetime.fromisoformat(supplied["scheduled_at"])+timedelta(hours=1)).isoformat())
            warning=await owner.post(path,json=uncertain)
            assert warning.status_code==409 and "explicitly confirm" in warning.json()["detail"]
            accepted=await owner.post(path,json={**uncertain,"confirm_eligible_unscored":True})
            assert accepted.status_code==201 and accepted.json()["unscored_confirmed"] is True
            listing=await owner.get(path)
            assert listing.status_code==200 and len(listing.json())==2
            assert len(db[InterviewSchedule])==2
            assert db[InterviewSchedule][0].screening_snapshot["screening_decision"]=="eligible"
            db[JobProfile][0].confirmed_snapshot=None
            assert (await owner.post(path,json=supplied)).status_code==409
            # Existing history is readable; editing approval does not silently cancel it.
            assert len((await owner.get(path)).json())==2
    asyncio.run(scenario())


def test_interview_migration_offline(capsys):
    command.upgrade(Config("alembic.ini"),"0003_candidate_scores:head",sql=True)
    sql=capsys.readouterr().out
    assert "CREATE TABLE interview_schedules" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql and "uq_initial_candidate_interview" in sql
    command.downgrade(Config("alembic.ini"),"head:0003_candidate_scores",sql=True)
    sql=capsys.readouterr().out
    assert "DROP TABLE interview_schedules" in sql and "DROP TABLE candidate_scores" not in sql
