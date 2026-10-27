"""Offline fake WebSockets only; no credentials, network or real speech."""
import asyncio
import json
from uuid import uuid4
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from app.core.config import Settings, ConfigurationError
from app.integrations.stt.assemblyai_live import AssemblyAILiveStream
from app.services.live_streaming_captions import LiveStreamingCaptions, ATTEMPTED


def turn(order=0, text='Synthetic final.', start=10, end=90, **patch):
    return dict(type='Turn',turn_order=order,transcript=text,end_of_turn=True,turn_is_formatted=True,
        words=[dict(start=start,end=end,word_is_final=True)],**patch)


class Socket:
    def __init__(self, *, finals=None, ack=True):
        self.q=asyncio.Queue(); self.sent=[]; self.closed=False
        self.finals=finals if finals is not None else [turn()]
        self.ack=ack
        self.q.put_nowait(json.dumps({'type':'Begin','configuration':{'model':'universal-streaming-english'}}))
    def __aiter__(self):return self
    async def __anext__(self):return await self.q.get()
    async def send(self,value):
        self.sent.append(value)
        if isinstance(value,str) and json.loads(value)['type']=='Terminate':
            for v in self.finals:self.q.put_nowait(json.dumps(v))
            if self.ack:self.q.put_nowait(json.dumps({'type':'Termination','audio_duration_seconds':.1,'session_duration_seconds':1}))
    async def close(self):self.closed=True


async def stream(ws, **kwargs):
    kwargs.setdefault('acknowledgement_timeout', .05)
    events=[]; failures=[]; calls=[]
    async def connector(url,**options):calls.append((url,options));return ws
    async def final(*value):events.append(value)
    p=AssemblyAILiveStream(SecretStr('fake'),final,failures.append,connector=connector,**kwargs)
    await p.start()
    return p,events,failures,calls


def test_live_config_is_separate_scoped_and_disabled_by_default():
    assert not Settings(_env_file=None).assemblyai_live_enabled
    base=dict(_env_file=None,assemblyai_live_enabled=True,livekit_synthetic_demo_enabled=True,
        assemblyai_api_key='fake',assemblyai_live_interview_id=uuid4())
    s=Settings(**base)
    assert not s.assemblyai_synthetic_enabled and not s.interview_copilot_enabled
    for patch in [dict(environment='production'),dict(assemblyai_synthetic_enabled=True),
                  dict(assemblyai_api_key=''),dict(assemblyai_live_interview_id=None),
                  dict(local_caption_model_path='synthetic')]:
        with pytest.raises(ConfigurationError):Settings(**{**base,**patch})


def test_real_pcm_finals_dedup_and_explicit_termination():
    async def run():
        partial={**turn(),'end_of_turn':False,'turn_is_formatted':False}
        unformatted={**turn(),'turn_is_formatted':False}
        ws=Socket(finals=[partial,unformatted,turn(),turn()])
        p,events,failures,calls=await stream(ws)
        await p.send(bytes(3200));await p.finish();await p.close()
        assert len(calls)==1 and 'format_turns=true' in calls[0][0]
        assert calls[0][1]['max_queue']==4 and 'Authorization' in calls[0][1]['additional_headers']
        assert calls[0][1]['logger'].disabled and not calls[0][1]['logger'].propagate
        assert len(events)==1 and events[0][1:]==(10,90) and not failures
        assert p.termination_confirmed and ws.closed and not p.pending_audio
        assert sum(isinstance(v,str) and json.loads(v)['type']=='Terminate' for v in ws.sent)==1
        with pytest.raises(ValueError):await p.start()
    asyncio.run(run())


@pytest.mark.parametrize('bad', [
    {**turn(),'words':[]}, {**turn(),'words':[{'start':-1,'end':90,'word_is_final':True}]},
    turn(end=101), {**turn(),'transcript':'private\x00'}, {**turn(),'turn_order':True},
])
def test_unverified_text_or_audio_intervals_never_publish(bad):
    async def run():
        p,events,failures,_=await stream(Socket(finals=[bad]))
        await p.send(bytes(3200))
        with pytest.raises(ValueError):await p.finish()
        await p.close(); assert not events and failures==['provider_error']
    asyncio.run(run())


def test_conflicting_final_is_not_a_second_stored_turn():
    async def run():
        p,events,failures,_=await stream(Socket(finals=[turn(),turn(text='Changed final.')]))
        await p.send(bytes(3200))
        with pytest.raises(ValueError):await p.finish()
        await p.close();assert len(events)==1 and failures
    asyncio.run(run())


def test_withdrawal_fences_finals_and_unacknowledged_cleanup_is_honest():
    async def run():
        for ack in [True,False]:
            ws=Socket(ack=ack)
            p,events,_,_=await stream(ws,acknowledgement_timeout=.2)
            await p.send(bytes(3200));await p.close()
            assert not events and ws.closed and p.termination_confirmed is ack
            assert not ack == (p.failure=='termination_unconfirmed')
    asyncio.run(run())


def test_incomplete_turn_and_provider_error_do_not_report_completion():
    async def run():
        for value in [{**turn(),'end_of_turn':False}, {'type':'Error','error':'DO_NOT_LOG'}]:
            p,_,_,_=await stream(Socket(finals=[value]))
            await p.send(bytes(3200))
            with pytest.raises(ValueError):await p.finish()
            await p.close()
            assert 'DO_NOT_LOG' not in str(p.__dict__)
    asyncio.run(run())


def test_provider_watchdog_terminates_without_new_audio():
    async def run():
        ws=Socket(finals=[])
        p,_,failures,_=await stream(ws,lifetime=.01)
        await asyncio.sleep(.03)
        await p.close()
        assert failures==['timeout'] and ws.closed and p.terminate_sent
    asyncio.run(run())


async def ready(*, storage=None):
    messages={role:[] for role in ('recruiter','candidate')}; workers={}; sockets={}
    clock=[100.0]
    def factory(role, final, failure):
        ws=sockets[role]=Socket(finals=[turn(text=f'Synthetic {role}.')])
        async def connect(*a,**k):return ws
        p=workers[role]=AssemblyAILiveStream(SecretStr('fake'),final,failure,connector=connect)
        return p
    s=LiveStreamingCaptions(factory,uuid4(),storage=storage,clock=lambda:clock[0])
    for role in messages:
        async def send(v,role=role):messages[role].append(v)
        await s.connect(role,send)
        s.authorization_checks[role]=AsyncMock()
    await s.approve('recruiter');assert not workers
    await s.approve('candidate')
    return s,workers,sockets,messages,clock


def test_independent_roles_storage_and_finish_use_shared_trusted_publisher():
    async def run():
        storage=SimpleNamespace(start=AsyncMock(),begin_finish=AsyncMock(),grace_until=None,
            caption=AsyncMock(),finish=AsyncMock(return_value={'kind':'storage','status':'saved','committed_turns':2}))
        s,workers,sockets,messages,clock=await ready(storage=storage)
        assert s.assistant is None and all(v[-1]['source']=='assemblyai-live' for v in messages.values())
        clock[0]+=.1
        for role in messages:await s.audio(role,bytes(3200))
        await s.request_finish('recruiter')
        for role in messages:
            await s.end_audio(role,dict(kind='end',frames=1,samples=1600,captured_samples=1600))
        await s.finalizer
        assert s.final_result['outcome']=='drained'
        events=[v for v in messages['recruiter'] if v['kind']=='caption']
        assert {e['role'] for e in events}=={'recruiter','candidate'}
        assert [e['sequence'] for e in events]==[1,2]
        assert all(0<=e['start']<e['end']<=.11 for e in events)
        assert storage.caption.await_count==2 and storage.finish.await_count==1
        assert all(ws.closed for ws in sockets.values())
        assert any(v['kind']=='provider-termination' and v['confirmed'] for v in messages['candidate'])
        with pytest.raises(ValueError):await s.audio('candidate',bytes(3200))
    asyncio.run(run())


def test_withdraw_rejects_late_text_and_duplicate_attempt():
    async def run():
        s,workers,sockets,messages,clock=await ready()
        clock[0]+=.1
        for role in messages:await s.audio(role,bytes(3200))
        await s.stop()
        assert not any(v['kind']=='caption' for v in messages['recruiter'])
        assert all(ws.closed for ws in sockets.values())
        duplicate=LiveStreamingCaptions(lambda *a:pytest.fail('No provider retry'),s.interview)
        for role in messages:await duplicate.connect(role,AsyncMock())
        await duplicate.approve('recruiter')
        with pytest.raises(ValueError):await duplicate.approve('candidate')
    asyncio.run(run())


def test_server_timeline_preserves_muted_gap_instead_of_recognition_latency():
    async def run():
        s,workers,sockets,messages,clock=await ready()
        clock[0]+=.1;await s.audio('recruiter',bytes(3200))
        clock[0]+=2;await s.audio('recruiter',bytes(3200))
        assert s._time('recruiter',1600)>1.9  # First sample after mute is not the prior frame end.
        assert s._time('recruiter',1600,is_end=True)<.11
        assert s._time('recruiter',1760)>2
        await s.stop()
    asyncio.run(run())


def test_reported_audio_coverage_cannot_be_invented_from_bytes_sent():
    async def run():
        s,_,_,messages,clock=await ready()
        clock[0]+=.2
        for role in messages:
            await s.audio(role,bytes(3200));await s.audio(role,bytes(3200))
        await s.request_finish('recruiter')
        for role in messages:await s.end_audio(role,dict(kind='end',frames=2,samples=3200,captured_samples=3200))
        await s.finalizer
        assert s.final_result['outcome']=='partial'
        assert all(v['processed_samples']==1600 for v in s.final_result['roles'].values())
    asyncio.run(run())


def test_closing_empty_turn_is_not_fabricated_and_small_tail_is_bounded():
    async def run():
        ws=Socket(finals=[{**turn(),'transcript':'','words':[]}])
        p,events,_,_=await stream(ws)
        await p.send(bytes(20));await p.finish();await p.close()
        assert not events and p.accepted_samples==10
        assert sum(len(frame) for frame in ws.sent if isinstance(frame,bytes))==1600
    asyncio.run(run())


def test_ninety_second_capture_guard_requests_normal_drain(monkeypatch):
    sleep=asyncio.sleep
    async def accelerated(seconds):await sleep(.02 if seconds==90 else seconds)
    monkeypatch.setattr(asyncio,'sleep',accelerated)
    async def run():
        s,_,sockets,messages,clock=await ready()
        clock[0]+=.1
        for role in messages:await s.audio(role,bytes(3200))
        await sleep(.04)
        assert s.finishing and any(e['kind']=='finishing' for e in messages['candidate'])
        for role in messages:await s.end_audio(role,dict(kind='end',frames=1,samples=1600,captured_samples=1600))
        await s.finalizer
        assert s.stopped and s.final_result['outcome']=='drained' and all(ws.closed for ws in sockets.values())
    asyncio.run(run())
