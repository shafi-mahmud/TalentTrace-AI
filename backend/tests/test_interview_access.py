"""Synthetic invitation/security regressions; no real Cloud calls."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from io import StringIO
from pydantic import ValidationError

from app.api.routers import interview_access as route
from app.core.auth import token_hash
from app.db.models.recruiter import InterviewInvitation, InterviewSchedule, JobProfile
from app.services.livekit_interview import join_window
from test_recruiter_records import workspace, client, login
from test_recruiter_records import SessionDouble
from fastapi import HTTPException, Response
from types import SimpleNamespace


@pytest.fixture
def invitation_workspace(monkeypatch, workspace):
    db, users, password = workspace
    job = JobProfile(id=uuid4(), recruiter_id=users[0].id, job_reference="TT-JOB-0123456789ABCDEF",
        job_title="Synthetic interview", revision=2, confirmed_snapshot={}, sources=[], suggestions={})
    interview = InterviewSchedule(id=uuid4(), recruiter_id=users[0].id, job_id=job.id,
        batch_id=uuid4(), upload_id=uuid4(), criteria_revision=2, scoring_version="f2-coverage-v1",
        scheduled_at=datetime.now(timezone.utc)+timedelta(minutes=1), timezone="UTC", duration_minutes=30,
        unscored_confirmed=False, screening_snapshot={})
    db[JobProfile]=[job];db[InterviewSchedule]=[interview]
    monkeypatch.setattr(route, "livekit_configuration", lambda: None)
    removed=[]
    async def remove(*args):removed.append(args)
    monkeypatch.setattr(route, "revoke_candidate_access", remove)
    calls=[]
    def issue(*args):
        calls.append(args)
        return {"server_url":"wss://synthetic.livekit.cloud", "token":"synthetic-token-"+"x"*40, "expires_in":args[3]}
    monkeypatch.setattr(route, "issue_interview_token", issue)
    route._attempts.clear()
    yield db,users,password,job,interview,calls,removed
    route._attempts.clear()


def test_single_use_hash_only_cookie_reconnect_owner_rotation_and_revoke(invitation_workspace):
    db,users,password,job,interview,calls,removed=invitation_workspace
    path=f"/api/v1/jobs/{job.id}/interviews/{interview.id}/invitation"
    async def scenario():
        async with client() as owner, client() as candidate, client() as foreign, client() as duplicate:
            assert (await candidate.post(path,json={})).status_code==401
            await login(owner,users[0],password);await login(foreign,users[1],password)
            assert (await foreign.post(path,json={})).status_code==404
            response=await owner.post(path,json={})
            assert response.status_code==200 and response.headers["cache-control"]=="no-store"
            raw=response.json()["token"];row=db[InterviewInvitation][0]
            assert row.token_hash==token_hash(raw) and raw not in repr(row.__dict__)
            claim=await candidate.post("/api/v1/interview-access/exchange",json={"token":raw})
            assert claim.json()=={"status":"ready"}
            cookie=claim.headers["set-cookie"]
            assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Path=/api/v1/interview-access" in cookie
            stored=db[InterviewInvitation][0]
            assert token_hash(candidate.cookies.get(route.COOKIE))==stored.candidate_session_hash
            assert (await duplicate.post("/api/v1/interview-access/exchange",json={"token":raw})).status_code==409
            assert (await duplicate.post("/api/v1/interview-access/livekit-token",json={"synthetic_test_confirmed":True})).status_code==401
            for _ in range(2):
                result=await candidate.post("/api/v1/interview-access/livekit-token",json={"synthetic_test_confirmed":True})
                assert result.status_code==200 and result.headers["cache-control"]=="no-store"
            assert calls[0]==calls[1] and calls[0][2]=="candidate"
            assert calls[0][1]==stored.id
            assert (await foreign.post(path+"/revoke")).status_code==404
            assert (await owner.post(path+"/revoke")).status_code==200
            assert removed==[(interview.id,stored.id)]
            assert (await candidate.get("/api/v1/interview-access/status")).status_code==401
            assert (await candidate.post("/api/v1/interview-access/livekit-token",json={"synthetic_test_confirmed":True})).status_code==401
            replacement=await owner.post(path,json={})
            assert replacement.status_code==200 and replacement.json()["token"]!=raw
            assert db[InterviewInvitation][0].id!=stored.id
            assert (await duplicate.post("/api/v1/interview-access/exchange",json={"token":raw})).status_code==401
    asyncio.run(scenario())


@pytest.mark.parametrize("failure",["expired","revoked","stale","inactive","owner_changed"])
def test_claim_fails_closed(failure,invitation_workspace):
    db,users,password,job,interview,_,_=invitation_workspace
    async def scenario():
        async with client() as owner,client() as candidate:
            await login(owner,users[0],password)
            raw=(await owner.post(f"/api/v1/jobs/{job.id}/interviews/{interview.id}/invitation",json={})).json()["token"]
            if failure=="expired":db[InterviewInvitation][0].expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
            if failure=="revoked":db[InterviewInvitation][0].revoked=True
            if failure=="stale":db[JobProfile][0].revision+=1
            if failure=="inactive":db[type(users[0])][0].active=False
            if failure=="owner_changed":db[JobProfile][0].recruiter_id=users[1].id
            result=await candidate.post("/api/v1/interview-access/exchange",json={"token":raw})
            assert result.status_code==401 and raw not in result.text
    asyncio.run(scenario())


def test_join_window_and_invalid_input_throttle_and_cloud_failure(monkeypatch,invitation_workspace):
    db,users,password,job,interview,_,_=invitation_workspace
    async def scenario():
        async with client() as owner,client() as candidate:
            await login(owner,users[0],password)
            path=f"/api/v1/jobs/{job.id}/interviews/{interview.id}/invitation"
            assert (await owner.post(path,json={"expires_in_hours":169})).status_code==422
            assert (await owner.post(path,json={"room":"arbitrary"})).status_code==422
            raw=(await owner.post(path,json={})).json()["token"]
            assert (await candidate.post("/api/v1/interview-access/exchange",json={"token":"x"*500})).status_code==422
            assert (await candidate.post("/api/v1/interview-access/exchange",json={"token":raw},headers={"Origin":"https://foreign.test"})).status_code==403
            assert (await candidate.post("/api/v1/interview-access/exchange",json={"token":raw})).status_code==200
            db[InterviewSchedule][0].scheduled_at=datetime.now(timezone.utc)+timedelta(hours=1)
            assert (await candidate.post("/api/v1/interview-access/livekit-token",json={"synthetic_test_confirmed":True})).status_code==409
            db[InterviewSchedule][0].scheduled_at=datetime.now(timezone.utc)-timedelta(hours=1)
            assert (await candidate.get("/api/v1/interview-access/status")).status_code==409
            async def broken(*args):raise RuntimeError("private credential")
            monkeypatch.setattr(route,"revoke_candidate_access",broken)
            result=await owner.post(path+"/revoke")
            assert result.status_code==502 and "private credential" not in result.text
            assert db[InterviewInvitation][0].revoked is True
            for _ in range(21):
                response=await candidate.post("/api/v1/interview-access/exchange",json={"token":"x"*43})
            assert response.status_code==429
    asyncio.run(scenario())


def test_window_boundaries(invitation_workspace):
    _,_,_,_,interview,_,_=invitation_workspace
    start=interview.scheduled_at
    with pytest.raises(ValueError):join_window(interview,start-timedelta(minutes=10,seconds=1))
    assert join_window(interview,start-timedelta(minutes=10))==300
    assert join_window(interview,start+timedelta(minutes=44,seconds=30))==30
    with pytest.raises(ValueError):join_window(interview,start+timedelta(minutes=45))


def test_migration_offline_hash_only():
    output=StringIO();config=Config("alembic.ini",output_buffer=output)
    command.upgrade(config,"0004_interview_schedules:head",sql=True)
    sql=output.getvalue()
    assert "interview_invitations" in sql and "candidate_session_hash" in sql
    assert "VARCHAR(64)" in sql and "UNIQUE (interview_id)" in sql
    assert "candidate_session_token" not in sql


def test_waiting_claim_refreshes_cached_invitation(invitation_workspace):
    """Model the actual PostgreSQL race: identity map precedes parent-lock wait."""
    db,_,_,_,interview,_,_=invitation_workspace
    raw="x"*43
    db[InterviewInvitation]=[InterviewInvitation(id=uuid4(),interview_id=interview.id,token_hash=token_hash(raw),
        expires_at=datetime.now(timezone.utc)+timedelta(hours=1),revoked=False,candidate_session_hash=None)]
    class CachedSession(SessionDouble):
        cached=None
        async def scalar(self,query):
            model=query.column_descriptions[0].get("entity")
            if model is JobProfile:
                # The first transaction commits while this request waits on the lock.
                self.rows[InterviewInvitation][0].candidate_session_hash="s"*64
            if model is InterviewInvitation and self.cached is not None and not query.get_execution_options().get("populate_existing"):
                return self.cached
            row=await super().scalar(query)
            if model is InterviewInvitation and self.cached is None:
                from copy import deepcopy
                self.cached=deepcopy(row)
                return self.cached
            return row
    async def scenario():
        with pytest.raises(HTTPException) as failure:
            await route.exchange(route.ExchangeRequest(token=raw),SimpleNamespace(client=SimpleNamespace(host="synthetic")),Response(),CachedSession(db))
        assert failure.value.status_code==409
    asyncio.run(scenario())
