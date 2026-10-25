"""Synthetic browser metadata and auth fixtures; no media or Cloud."""
import asyncio
from uuid import uuid4,UUID
import pytest
from fastapi import HTTPException
from app.api.routers import interview_attention as route
from test_interview_access import invitation_workspace
from test_recruiter_records import client,login,workspace


def test_state_is_bounded_isolated_and_old_events_cannot_restore_withdrawal():
    async def run():
        clock=[0];store=route.ActivityStore(lambda:clock[0]);a,b=uuid4(),uuid4();ia,ib=(uuid4(),'hash-a'),(uuid4(),'hash-b')
        ra=store.start(a,ia);rb=store.start(b,ib)
        store.update(a,ia,route.Signal(run_id=ra,visibility='hidden',fullscreen='inactive'))
        assert store.view(a,ia)['visibility']=='hidden'
        assert store.view(b,ib)['visibility']=='unsupported'
        store.withdraw(a,ia,ra)
        with pytest.raises(HTTPException):store.update(a,ia,route.Signal(run_id=ra,visibility='visible',fullscreen='active'))
        assert store.view(b,ib)['state']=='shared'
        newer=store.start(a,ia);store.withdraw(a,ia,ra)
        assert store.checked(a,ia)['run_id']==newer
        clock[0]=31;assert store.view(a,ia)=={'state':'not_shared'}
        assert store.view(b,ib)=={'state':'not_shared'}
    asyncio.run(run())


def test_consent_owner_isolation_revocation_and_no_extra_browser_data(invitation_workspace,monkeypatch):
    _,users,password,job,interview,_,_=invitation_workspace
    monkeypatch.setattr(route,'store',route.ActivityStore())
    async def run():
        async with client() as owner,client() as candidate,client() as other:
            await login(owner,users[0],password);await login(other,users[1],password)
            invitation=f'/api/v1/jobs/{job.id}/interviews/{interview.id}/invitation'
            raw=(await owner.post(invitation,json={})).json()['token']
            await candidate.post('/api/v1/interview-access/exchange',json={'token':raw})
            path=f'/api/v1/jobs/{job.id}/interviews/{interview.id}/attention'
            assert (await owner.get(path)).json()=={'state':'not_shared'}
            before={'run_id':str(uuid4()),'visibility':'visible','fullscreen':'inactive'}
            assert (await candidate.post('/api/v1/interview-access/attention',json=before)).status_code==409
            consent=await candidate.post('/api/v1/interview-access/attention/consent',json={'version':'attention-v1','decision':'accept'});assert consent.status_code==200
            signal={**before,'run_id':consent.json()['run_id']}
            assert (await candidate.post('/api/v1/interview-access/attention',json={**signal,'url':'PRIVATE'})).status_code==422
            assert (await candidate.post('/api/v1/interview-access/attention',json=signal)).status_code==200
            assert (await owner.get(path)).json()=={'state':'shared','visibility':'visible','fullscreen':'inactive'}
            assert (await other.get(path)).status_code==404
            assert (await candidate.get(path)).status_code==401
            assert (await candidate.post('/api/v1/interview-access/attention/withdraw',json={'run_id':signal['run_id']})).status_code==200
            assert (await candidate.post('/api/v1/interview-access/attention',json=signal)).status_code==409
            consent=(await candidate.post('/api/v1/interview-access/attention/consent',json={'version':'attention-v1','decision':'accept'})).json()
            await owner.post(invitation+'/revoke')
            assert (await candidate.post('/api/v1/interview-access/attention',json={**signal,'run_id':consent['run_id']})).status_code==401
            assert (await owner.get(path)).json()=={'state':'not_shared'}
            assert not route.store.records
    asyncio.run(run())
