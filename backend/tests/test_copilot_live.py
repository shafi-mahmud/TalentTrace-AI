"""Synthetic recognized-event integration; no real STT/model/browser/provider."""
import asyncio
from dataclasses import replace
import threading
from uuid import uuid4
import pytest
from app.services.copilot_live import LiveBridge
from app.services.interview_captions import CaptionSession
from test_copilot_delivery import offline, runtime, consent


async def ready(runtime):
    manager,access,clock=runtime
    messages={'recruiter':[],'candidate':[]}
    words=iter(['Explain Python lists.','Lists are mutable ordered sequences.',
        'For example, append adds an item to a list.'])
    class Worker:
        async def start(self):pass
        async def close(self):pass
        async def transcribe(self,audio):return next(words)
    caption=CaptionSession(Worker)
    for role in messages:
        async def send(value,role=role):messages[role].append(value)
        await caption.connect(role,send)
    await caption.approve('recruiter');await caption.approve('candidate')
    caption.started_wall=100
    calls=[]
    async def authorize():calls.append('fresh');return access
    bridge=LiveBridge(access.interview,caption.caption_run_id,manager,authorize,settle=.01)
    caption.assistant=bridge
    manager.prepare(access,caption_run_id=caption.caption_run_id)
    return manager,access,clock,caption,bridge,messages,calls


async def idle(bridge):
    task=bridge.task
    if task:await asyncio.wait_for(asyncio.shield(task),3)


def event(sequence,text,role='candidate',start=2,end=3):
    return dict(kind='caption',sequence=sequence,role=role,start=start,end=end,text=text)


def test_actual_decode_hook_attribution_suggestion_and_private_delivery(runtime):
    async def scenario():
        manager,access,clock,s,b,messages,calls=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        await s._decode('recruiter',bytes(3200),.1,1)
        await s._decode('candidate',bytes(3200),1.1,2)
        await idle(b)
        result=manager.view(access,recruiter=True)
        assert result['live_connected'] and result['suggestion']['requirement']=='Python'
        assert calls==['fresh','fresh']
        assert [(r.role,r.audio_start_ms,r.audio_end_ms) for r in b.records]==[('recruiter',100,1000),('candidate',1100,2000)]
        assert all(r.source.caption_run_id==s.caption_run_id for r in b.records)
        assert 'suggestion' not in manager.view(access)
        for received in messages.values():
            captions=[v for v in received if v['kind']=='caption']
            assert len(captions)==2 and all(set(v)=={'kind','role','sequence','start','end','text'} for v in captions)
        clock[0]=122
        await s._decode('candidate',bytes(3200),2.1,3)
        assert manager.view(access,recruiter=True)['suggestion'] is None
        await idle(b)
        assert manager.view(access,recruiter=True)['suggestion']['requirement']=='SQL'
        await s.stop()
        assert manager.view(access)['status']=='withdrawn' and not b.records
    asyncio.run(scenario())


def test_no_preconsent_audio_even_if_recognition_returns_after_consent(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        await s._decode('recruiter',bytes(3200),.1,1)
        assert not b.records and b.task is None
        clock[0]=103
        consent(manager,access,'recruiter');consent(manager,access,'candidate')
        await s._decode('candidate',bytes(3200),1.1,2) # recognized late, original audio before 103
        assert not b.records and b.task is None
        await s.stop()
    asyncio.run(scenario())


@pytest.mark.parametrize('answer,status',[('I travelled by bus.','abstained'),('[uncertain speech]','abstained'),
    ('Python lists are ...','waiting')])
def test_unsafe_or_unfinished_speech(runtime,answer,status):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        b.offer(s.caption_run_id,100,event(1,'Explain Python lists.','recruiter',.1,1))
        b.offer(s.caption_run_id,100,event(2,answer,'candidate',1.1,2))
        await idle(b)
        result=manager.view(access,recruiter=True)
        assert result['processing']==status and result['suggestion'] is None
        await s.stop()
    asyncio.run(scenario())


def test_duplicate_wrong_run_and_out_of_order_are_ignored(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        first=event(1,'Explain Python lists.','recruiter',.1,1)
        b.offer(s.caption_run_id,100,first);b.offer(s.caption_run_id,100,first)
        b.offer(uuid4(),100,event(9,'wrong run'))
        b.offer(s.caption_run_id,100,event(2,'Lists are mutable.','candidate',1.1,2))
        b.offer(s.caption_run_id,100,event(3,'old audio','candidate',.1,.5))
        await idle(b)
        assert [r.source.sequence for r in b.records]==[1,2]
        assert manager.view(access,recruiter=True)['suggestion']
        await s.stop()
    asyncio.run(scenario())


def test_caption_replacement_invalidates_consent_and_old_event_identity(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate')
        replacement=LiveBridge(access.interview,uuid4(),manager,b.authorize,settle=.01)
        assert manager.view(access)['status']=='withdrawn'
        replacement.offer(s.caption_run_id,100,event(1,'old run'))
        assert not replacement.records
        b.close();replacement.close();await s.stop()
    asyncio.run(scenario())


def test_slow_graph_does_not_block_caption_and_withdrawal_drops_inflight(runtime):
    async def scenario():
        manager,access,clock,s,b,messages,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        entered=threading.Event();release=threading.Event();run=manager.runs[access.interview]
        original=run.logic.process
        def slow(**kwargs):entered.set();assert release.wait(3);return original(**kwargs)
        run.logic.process=slow
        await asyncio.wait_for(s._decode('recruiter',bytes(3200),.1,1),.5)
        await asyncio.wait_for(s._decode('candidate',bytes(3200),1.1,2),.5)
        for _ in range(100):
            if entered.is_set():break
            await asyncio.sleep(.01)
        assert entered.is_set() and len([e for e in messages['candidate'] if e['kind']=='caption'])==2
        manager.invalidate(access.interview)
        assert not b.records and manager.view(access,recruiter=True)['suggestion'] is None
        release.set();await asyncio.sleep(.1)
        await s.stop()
        assert manager.view(access,recruiter=True)['suggestion'] is None
    asyncio.run(scenario())


@pytest.mark.parametrize('failure',['authority','interview','graph'])
def test_failures_never_stop_f4(runtime,failure):
    async def scenario():
        manager,access,clock,s,b,messages,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        async def bad_auth():
            if failure=='authority':raise ValueError('private diagnostic')
            return replace(access,interview=uuid4())
        if failure!='graph':b.authorize=bad_auth
        else:
            def bad_graph(**kwargs):raise RuntimeError('private diagnostic')
            manager.runs[access.interview].logic.process=bad_graph
        await s._decode('recruiter',bytes(3200),.1,1)
        await s._decode('candidate',bytes(3200),1.1,2)
        await idle(b)
        assert not s.stopped and not b.records and manager.view(access)['status']=='withdrawn'
        assert len([e for e in messages['candidate'] if e['kind']=='caption'])==2
        await s.stop()
    asyncio.run(scenario())


def test_finalization_closes_assistant_before_storage_drain(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate')
        await s.request_finish('recruiter')
        assert b.closed and manager.view(access)['status']=='withdrawn'
        for role in ('recruiter','candidate'):
            await s.end_audio(role,dict(kind='end',frames=0,samples=0,captured_samples=0))
        await s.finalizer
        assert s.final_result['outcome']=='drained'
    asyncio.run(scenario())



def test_one_sided_consent_and_submillisecond_preconsent_cutoff(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter')
        b.offer(s.caption_run_id,100,event(1,'Explain Python lists.','recruiter',.1,1))
        assert not b.records
        clock[0]=103.0005;consent(manager,access,'candidate');clock[0]=106
        b.offer(s.caption_run_id,100,event(2,'Lists are mutable.','candidate',3.0004,4))
        assert not b.records # No rounding down the actual consent instant.
        await s.stop()
    asyncio.run(scenario())


def test_authorization_changed_during_calculation_prevents_publication(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
        count=0
        async def authorize():
            nonlocal count
            count+=1
            return access if count==1 else replace(access,revision=3)
        b.authorize=authorize
        await s._decode('recruiter',bytes(3200),.1,1);await s._decode('candidate',bytes(3200),1.1,2)
        await idle(b)
        assert count==2 and manager.view(access,recruiter=True)['suggestion'] is None
        assert not s.stopped and not b.records
        await s.stop()
    asyncio.run(scenario())


def test_bound_overflow_clears_assistant_without_stopping_caption(runtime):
    async def scenario():
        manager,access,clock,s,b,_,_=await ready(runtime)
        consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=120
        for i in range(16):
            b.offer(s.caption_run_id,100,event(i+1,'Python lists are mutable.','candidate',i+.1,i+1))
        assert b.closed and not b.records and not s.stopped
        await s.stop()
    asyncio.run(scenario())


def test_offer_failure_cannot_interrupt_decode_or_storage(runtime):
    async def scenario():
        manager,access,clock,s,b,messages,_=await ready(runtime)
        class Broken:
            def offer(self,*args):raise RuntimeError('private')
            def close(self):pass
        class Storage:
            def __init__(self):self.seen=[]
            async def caption(self,event):self.seen.append(event)
            async def finish(self,result):return {'kind':'storage','status':'saved'}
        s.assistant=Broken();s.storage=Storage()
        await s._decode('recruiter',bytes(3200),.1,1)
        assert not s.stopped and len(s.storage.seen)==1
        assert len([e for e in messages['candidate'] if e['kind']=='caption'])==1
        b.close();await s.stop()
    asyncio.run(scenario())



# Exercise the existing real HTTP auth boundary when live mode is gated on.
from test_copilot_delivery import api, setup
from test_recruiter_records import workspace, client
from test_interview_access import invitation_workspace


def test_live_prepare_requires_current_caption_and_pins_its_identity(api,monkeypatch):
    from app.core.config import settings
    from app.api.routers import interview_captions
    from types import SimpleNamespace
    async def scenario():
        async with client() as owner,client() as candidate:
            root,_=await setup(api,owner,candidate)
            monkeypatch.setattr(settings,'interview_copilot_live_enabled',True)
            monkeypatch.setattr(settings,'livekit_synthetic_demo_enabled',True)
            monkeypatch.setattr(interview_captions,'sessions',{})
            assert (await owner.post(root+'/prepare',json={})).status_code==409
            interview=api[4];manager=api[5];run_id=uuid4()
            caption=SimpleNamespace(stopped=False,finishing=False,caption_run_id=run_id,assistant=SimpleNamespace(closed=False))
            interview_captions.sessions[interview.id]=caption
            response=await owner.post(root+'/prepare',json={})
            assert response.status_code==200
            assert manager.runs[interview.id].binding.caption_run_id==run_id
            assert manager.runs[interview.id].live
            caption.stopped=True
            assert (await owner.post(root+'/prepare',json={})).status_code==409
    asyncio.run(scenario())
