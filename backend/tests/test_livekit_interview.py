"""Local SDK signing and mocked failures only; zero LiveKit network calls."""
import asyncio
from datetime import datetime,timedelta,timezone
from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.db.models.recruiter import JobProfile,InterviewSchedule
from app.services import livekit_interview as service
from app.api.routers import interviews as route
from test_recruiter_records import workspace,client,login


def configuration(**changes):
    return Settings(_env_file=None,**{"livekit_url":"wss://synthetic.livekit.cloud", "livekit_api_key":"synthetic-api-key",
        "livekit_api_secret":"s"*64,"livekit_synthetic_demo_enabled":True,**changes})


def test_explicit_local_development_only_loopback(monkeypatch):
    monkeypatch.setattr(service,'settings',configuration(livekit_local_development_enabled=True,livekit_url='ws://127.0.0.1:7880'))
    assert service.issue_interview_token(uuid4(),uuid4(),'recruiter')['server_url']=='ws://127.0.0.1:7880'
    for url in ['ws://localhost:7880','ws://192.168.1.2:7880','ws://127.0.0.1:9000','ws://127.0.0.1:7880/?token=x']:
        monkeypatch.setattr(service,'settings',configuration(livekit_local_development_enabled=True,livekit_url=url))
        with pytest.raises(service.LiveKitUnavailable):service.livekit_configuration()


def test_real_sdk_grants_ttl_and_opaque_two_slots(monkeypatch):
    monkeypatch.setattr(service,"settings",configuration())
    interview,owner=uuid4(),uuid4()
    a=service.issue_interview_token(interview,owner,"recruiter")
    b=service.issue_interview_token(interview,owner,"candidate")
    ca=jwt.decode(a["token"],"s"*64,algorithms=["HS256"],issuer="synthetic-api-key")
    cb=jwt.decode(b["token"],"s"*64,algorithms=["HS256"],issuer="synthetic-api-key")
    assert ca["exp"]-ca["nbf"]==300
    assert ca["video"]["room"]==cb["video"]["room"] and ca["sub"]!=cb["sub"]
    assert str(interview) not in ca["video"]["room"] and str(owner) not in ca["sub"]
    assert ca["video"]["roomJoin"] is True and ca["video"]["canSubscribe"] is True
    assert ca["video"]["canPublishSources"]==["camera","microphone"]
    for grant in ("roomAdmin","roomCreate","roomList","roomRecord","canPublishData","canUpdateOwnMetadata"):
        assert ca["video"][grant] is False
    assert "metadata" not in ca and "name" not in ca
    assert set(a)=={"server_url","token","expires_in"}


@pytest.mark.parametrize("changes",[{"livekit_synthetic_demo_enabled":False},{"environment":"production"},
    {"livekit_api_key":None},{"livekit_api_secret":None},{"livekit_url":"ws://localhost:7880"},
    {"livekit_url":"wss://secret@synthetic.livekit.cloud"},{"livekit_url":"wss://synthetic.livekit.cloud/?token=private"}])
def test_configuration_fails_closed(monkeypatch,changes):
    monkeypatch.setattr(service,"settings",configuration(**changes))
    with pytest.raises(service.LiveKitUnavailable):service.issue_interview_token(uuid4(),uuid4(),"recruiter")


def test_signer_cannot_issue_third_slot(monkeypatch):
    monkeypatch.setattr(service,"settings",configuration())
    with pytest.raises(service.LiveKitUnavailable):service.issue_interview_token(uuid4(),uuid4(),"untrusted")


def test_short_remaining_window_limits_token_expiry(monkeypatch):
    monkeypatch.setattr(service,"settings",configuration())
    signed=service.issue_interview_token(uuid4(),uuid4(),"candidate",30)
    claims=jwt.decode(signed["token"],"s"*64,algorithms=["HS256"])
    assert claims["exp"]-claims["nbf"]==30 and signed["expires_in"]==30


def test_cloud_revoke_uses_scoped_identity_and_explicit_cutoff(monkeypatch):
    from livekit import api
    from types import SimpleNamespace
    import time
    monkeypatch.setattr(service,"settings",configuration())
    interview,invitation=uuid4(),uuid4();calls=[]
    async def remove(body):calls.append(body)
    class Client:
        def __init__(self,**kwargs):self.room=SimpleNamespace(remove_participant=remove)
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
    monkeypatch.setattr(api,"LiveKitAPI",Client)
    asyncio.run(service.revoke_candidate_access(interview,invitation))
    room,identity=service.room_identity(interview,invitation,"candidate")
    assert calls[0].room==room and calls[0].identity==identity
    assert int(time.time())<=calls[0].revoke_token_ts<=int(time.time())+2


def test_owner_synthetic_confirmations_stale_and_sanitized_failures(monkeypatch,workspace):
    db,users,password=workspace
    job=JobProfile(id=uuid4(),recruiter_id=users[0].id,job_reference="TT-JOB-0123456789ABCDEF",job_title="Synthetic job",
        revision=2,confirmed_snapshot={},sources=[],suggestions={})
    schedule=InterviewSchedule(id=uuid4(),recruiter_id=users[0].id,job_id=job.id,batch_id=uuid4(),upload_id=uuid4(),
        criteria_revision=2,scoring_version="f2-coverage-v1",scheduled_at=datetime.now(timezone.utc)+timedelta(minutes=1),
        timezone="UTC",duration_minutes=30,unscored_confirmed=False,screening_snapshot={})
    db[JobProfile]=[job];db[InterviewSchedule]=[schedule]
    calls=[]
    def issue(*args):calls.append(args);return {"server_url":"wss://synthetic.livekit.cloud","token":"synthetic-token-"+"x"*40,"expires_in":300}
    monkeypatch.setattr(route,"issue_interview_token",issue)
    path=f"/api/v1/jobs/{job.id}/interviews/{schedule.id}/livekit-token"
    body={"synthetic_test_confirmed":True}
    async def scenario():
        async with client() as owner,client() as foreign,client() as anonymous:
            assert (await anonymous.post(path,json=body)).status_code==401
            await login(owner,users[0],password);await login(foreign,users[1],password)
            assert (await foreign.post(path,json=body)).status_code==404
            assert (await owner.post(path.replace(str(schedule.id),str(uuid4())),json=body)).status_code==404
            assert not calls
            for patch in ({"slot":"c"},{"synthetic_test_confirmed":False},{"synthetic_test_confirmed":1},{"room":"arbitrary"},{"api_key":"private"}):
                assert (await owner.post(path,json={**body,**patch})).status_code==422
            result=await owner.post(path,json=body)
            assert result.status_code==200 and result.headers["cache-control"]=="no-store"
            assert calls==[(schedule.id,users[0].id,"recruiter",300)]
            assert len(db[InterviewSchedule])==1 and "token" not in db[InterviewSchedule][0].screening_snapshot
            db[JobProfile][0].revision=3
            assert (await owner.post(path,json=body)).status_code==409
            db[JobProfile][0].revision=2
            def unavailable(*args):raise service.LiveKitUnavailable()
            monkeypatch.setattr(route,"issue_interview_token",unavailable)
            assert (await owner.post(path,json=body)).status_code==503
            def failure(*args):raise RuntimeError("private credential/configuration details")
            monkeypatch.setattr(route,"issue_interview_token",failure)
            failed=await owner.post(path,json=body)
            assert failed.status_code==502 and failed.json()=={"detail":"Interview access could not be issued."}
    asyncio.run(scenario())
