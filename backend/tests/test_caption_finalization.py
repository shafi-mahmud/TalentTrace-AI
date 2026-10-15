"""Synthetic RAM-only PCM and mocked recognizers. No models, media or DB."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.services import interview_captions as service
from app.api.routers import interview_captions as route


class Worker:
    def __init__(self): self.sizes=[]; self.closed=False
    async def start(self): pass
    async def close(self): self.closed=True
    async def transcribe(self, pcm): self.sizes.append(len(pcm)); return 'Synthetic result'


async def ready(worker=Worker):
    workers=[]; messages={role:[] for role in service.ROLES}
    def factory():
        value=worker(); workers.append(value); return value
    session=service.CaptionSession(factory)
    for role in service.ROLES:
        async def send(value, role=role): messages[role].append(value)
        await session.connect(role,send)
    await session.approve('recruiter'); await session.approve('candidate')
    return session,workers,messages


async def end(session,role,**patch):
    await session.end_audio(role,dict(kind='end',frames=session.frames[role],
        samples=session.accepted_samples[role],captured_samples=session.accepted_samples[role],**patch))


async def finish(session):
    await session.request_finish('recruiter')
    for role in service.ROLES: await end(session,role)
    await session.finalizer


@pytest.mark.parametrize('frames,tail',[(0,0),(40,0),(7,0),(0,2),(39,3198)])
def test_normal_empty_full_and_partial_are_drained_once(frames,tail):
    async def scenario():
        s,workers,messages=await ready()
        for _ in range(frames): await s.audio('candidate',bytes(3200))
        await s.request_finish('candidate')
        if tail: await s.audio('candidate',bytes(tail))
        await end(s,'candidate');await end(s,'recruiter');await s.finalizer
        assert s.final_result['outcome']=='drained'
        assert s.accepted_samples['candidate']==s.processed_samples['candidate']==frames*1600+tail//2
        assert sum(sum(w.sizes) for w in workers)==frames*3200+tail
        for events in messages.values():
            terminal=next(i for i,e in enumerate(events) if e['kind']=='finalized')
            assert all(i<terminal for i,e in enumerate(events) if e['kind']=='caption')
        assert all(w.closed for w in workers) and not any(s.buffers.values()) and not s.providers
    asyncio.run(scenario())


def test_pending_and_inflight_two_roles_duplicate_finish_and_end():
    async def scenario():
        release=asyncio.Event();started=0;both=asyncio.Event()
        class Slow(Worker):
            async def transcribe(self,pcm):
                nonlocal started
                started+=1
                if started==2: both.set()
                await release.wait();return await super().transcribe(pcm)
        s,workers,_=await ready(Slow)
        for role in service.ROLES:
            for _ in range(39):await s.audio(role,bytes(3200))
        tasks=[asyncio.create_task(s.audio(role,bytes(3200))) for role in service.ROLES]
        await both.wait()
        for role in service.ROLES:
            for _ in range(2):await s.audio(role,bytes(3200))
        await s.request_finish('candidate'); original=s.finalizer
        await s.request_finish('recruiter');assert s.finalizer is original
        for role in service.ROLES: await end(s,role);await end(s,role)
        assert not original.done();release.set()
        await asyncio.gather(*tasks);await original
        assert s.final_result['outcome']=='drained'
        assert all(n==67200 for n in s.processed_samples.values())
        assert all(w.sizes==[128000,6400] and w.closed for w in workers)
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',['timeout','recognizer','withdraw','authorization','overflow'])
def test_failure_during_finish_never_claims_drained(monkeypatch,failure):
    async def scenario():
        class Failed(Worker):
            async def transcribe(self,pcm):
                if failure=='recognizer': raise RuntimeError('private synthetic failure')
                if failure=='timeout': await asyncio.Event().wait()
                return await super().transcribe(pcm)
        if failure=='timeout':monkeypatch.setattr(service,'FINALIZATION_SECONDS',.03)
        s,workers,messages=await ready(Failed)
        await s.audio('candidate',bytes(3200))
        await s.request_finish('candidate')
        if failure=='authorization':
            async def denied():raise ValueError('Access changed')
            s.authorization_checks={role:denied for role in service.ROLES}
        if failure=='withdraw': await s.stop()
        elif failure=='overflow':
            # No unbounded capacity is granted during finalization.
            s.buffers['candidate'].extend(bytes(128000-3200))
            await s.audio('candidate',bytes(3200))
        else:
            for role in service.ROLES:await end(s,role)
        await asyncio.gather(s.finalizer,return_exceptions=True)
        await s.stop()
        assert s.final_result['outcome'] in ('partial','failed')
        assert all(w.closed for w in workers) and not any(s.buffers.values())
        assert 'private synthetic failure' not in str(messages)
    asyncio.run(scenario())


def test_missing_peer_end_times_out_and_bad_counts_are_rejected(monkeypatch):
    async def scenario():
        monkeypatch.setattr(service,'FINALIZATION_SECONDS',.03)
        s,workers,_=await ready();await s.request_finish('candidate')
        with pytest.raises(ValueError):
            await s.end_audio('candidate',dict(kind='end',frames=1,samples=1600,captured_samples=1600))
        await end(s,'candidate');await s.finalizer
        assert s.final_result['outcome']=='failed' and all(w.closed for w in workers)
    asyncio.run(scenario())


def test_partial_audio_only_at_normal_end_and_no_audio_after_end():
    async def scenario():
        s,_,_=await ready()
        with pytest.raises(ValueError):await s.audio('candidate',bytes(100))
        await s.request_finish('candidate');await s.audio('candidate',bytes(100))
        with pytest.raises(ValueError):await s.audio('candidate',bytes(3200))
        await end(s,'candidate')
        with pytest.raises(ValueError):await s.audio('candidate',bytes(100))
        await end(s,'recruiter');await s.finalizer
        assert s.processed_samples['candidate']==50
    asyncio.run(scenario())


def test_silence_is_processed_without_inventing_text():
    async def scenario():
        class Silent(Worker):
            async def transcribe(self,pcm):self.sizes.append(len(pcm));return ''
        s,_,_=await ready(Silent);await s.audio('candidate',bytes(3200));await finish(s)
        assert s.processed_samples['candidate']==1600 and s.caption_events['candidate']==0
        assert s.final_result['outcome']=='drained'
    asyncio.run(scenario())


@pytest.mark.parametrize('revoke,disconnect',[(False,False),(True,False),(False,True)])
def test_authenticated_websocket_finish_and_fail_closed(monkeypatch,revoke,disconnect):
    key=uuid4();identity=uuid4();expiry=datetime.now(timezone.utc)+timedelta(minutes=5)
    allowed=[True];workers=[]
    async def authorized(*_):
        if not allowed[0]:raise ValueError('Denied')
        return key,'candidate',identity,expiry
    async def seed():
        def factory():w=Worker();workers.append(w);return w
        s=service.CaptionSession(factory)
        async def send(_):pass
        await s.connect('recruiter',send);await s.approve('recruiter')
        async def recruiter_check():
            if not allowed[0]:raise ValueError('Denied')
        s.authorization_checks['recruiter']=recruiter_check
        return s
    s=asyncio.run(seed());route.sessions[key]=s
    monkeypatch.setattr(route,'trusted_socket',lambda _:True);monkeypatch.setattr(route,'authorize',authorized)
    try:
        with TestClient(app) as client:
            with client.websocket_connect('/api/v1/interview-access/captions') as ws:
                assert ws.receive_json()['kind']=='waiting'
                ws.send_text('consent');assert ws.receive_json()['kind']=='active'
                if disconnect:
                    ws.close()
                else:
                    allowed[0]=not revoke;ws.send_text('finish')
                    if revoke:assert ws.receive_json()['kind']=='stopped'
                    else:
                        assert ws.receive_json()['kind']=='finishing'
                        ws.send_bytes(bytes(100))
                        ws.send_text('{"kind":"end","frames":1,"samples":50,"captured_samples":50}')
                        assert ws.receive_json()=={'kind':'accepted','frames':1,'samples':50}
                        # A second browser freezes and sends its end marker.
                        client.portal.call(end,s,'recruiter')
                        assert ws.receive_json()['kind']=='caption'
                        assert ws.receive_json()['outcome']=='drained'
                        assert ws.receive_json()['kind']=='stopped'
        assert s.stopped and all(w.closed for w in workers)
        if revoke or disconnect:assert not any(s.processed_samples.values())
    finally:route.sessions.clear()
