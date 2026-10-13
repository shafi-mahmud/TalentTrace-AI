"""Offline synthetic PCM/provider tests; no Cloud, microphone, model or DB call."""
import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import httpx
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app.services.interview_captions import CaptionSession
from app.api.routers import interview_captions as route
from app.integrations.stt.local_whisper import LocalWhisper


@pytest.fixture(autouse=True)
def no_provider_network(monkeypatch):
    async def forbidden(*args, **kwargs):pytest.fail("Offline caption tests must not contact providers")
    monkeypatch.setattr(httpx.AsyncClient, "send", forbidden)


class Provider:
    def __init__(self):
        self.started = False
        self.closed = False
        self.frames = []
        self.text = "Synthetic caption"
    async def start(self): self.started = True
    async def close(self): self.closed = True
    async def transcribe(self, pcm):
        self.frames.append(pcm)
        return self.text


def test_both_consents_separate_roles_bounded_pcm_and_withdrawal():
    async def scenario():
        providers, events = [], []
        def factory():
            p = Provider(); providers.append(p); return p
        async def send(v): events.append(v)
        session = CaptionSession(factory)
        await session.connect("recruiter", send);await session.connect("candidate", send)
        with pytest.raises(ValueError): await session.audio("recruiter", bytes(3200))
        await session.approve("recruiter");assert not providers
        await session.approve("candidate");assert len(providers)==2
        for role in ("recruiter", "candidate"):
            for _ in range(40): await session.audio(role, bytes(3200))
        captions=[e for e in events if e["kind"]=="caption"]
        assert {e["role"] for e in captions}=={"recruiter","candidate"}
        assert all(e["start"]<=e["end"] and e["sequence"]>0 for e in captions)
        assert all(len(p.frames)==1 and len(p.frames[0])==128000 for p in providers)
        await session.stop();assert all(p.closed for p in providers)
        assert not session.consent and all(not b for b in session.buffers.values())
        with pytest.raises(ValueError):await session.audio("candidate", bytes(3200))
    asyncio.run(scenario())


def test_timeout_duplicate_role_and_invalid_frame():
    async def scenario():
        now=[0];session=CaptionSession(Provider,clock=lambda:now[0])
        async def send(v):pass
        await session.connect("recruiter",send)
        with pytest.raises(ValueError):await session.connect("recruiter",send)
        with pytest.raises(ValueError):await session.connect("admin",send)
        await session.connect("candidate",send)
        await session.approve("recruiter");await session.approve("candidate")
        with pytest.raises(ValueError):await session.audio("candidate",bytes(64001))
        now[0]=120;await session.audio("candidate",bytes(3200));assert session.stopped
    asyncio.run(scenario())


def test_withdraw_during_inference_discards_late_caption():
    async def scenario():
        entered, finish=asyncio.Event(),asyncio.Event();events=[]
        class Slow(Provider):
            async def transcribe(self,pcm):entered.set();await finish.wait();return "Late caption"
        async def send(v):events.append(v)
        s=CaptionSession(Slow);await s.connect("recruiter",send);await s.connect("candidate",send)
        await s.approve("recruiter");await s.approve("candidate")
        for _ in range(39):await s.audio("candidate",bytes(3200))
        task=asyncio.create_task(s.audio("candidate",bytes(3200)));await entered.wait()
        await s.stop();finish.set();await task
        assert not any(e["kind"]=="caption" for e in events)
    asyncio.run(scenario())


@pytest.mark.parametrize("text",["unsafe\x00text","x"*1001])
def test_invalid_provider_text_stops_without_output(text):
    async def scenario():
        events=[]
        def factory():p=Provider();p.text=text;return p
        async def send(v):events.append(v)
        s=CaptionSession(factory);await s.connect("recruiter",send);await s.connect("candidate",send)
        await s.approve("recruiter");await s.approve("candidate")
        for _ in range(40):await s.audio("candidate",bytes(3200))
        assert s.stopped and not any(e["kind"]=="caption" for e in events)
    asyncio.run(scenario())


def test_missing_model_fails_offline(tmp_path):
    with pytest.raises(ValueError):asyncio.run(LocalWhisper(tmp_path).start())


@pytest.mark.parametrize("stage",["start","transcribe"])
def test_provider_failure_is_stopped_and_does_not_expose_details(stage):
    async def scenario():
        events=[]
        class Failed(Provider):
            async def start(self):
                if stage=="start":raise RuntimeError("PRIVATE provider details")
            async def transcribe(self,pcm):raise RuntimeError("PRIVATE provider details")
        async def send(v):events.append(v)
        s=CaptionSession(Failed);await s.connect("recruiter",send);await s.connect("candidate",send)
        await s.approve("recruiter");await s.approve("candidate")
        if stage=="transcribe":
            for _ in range(40):await s.audio("candidate",bytes(3200))
        assert s.stopped and "PRIVATE" not in str(events)
        assert not any(e["kind"]=="caption" for e in events)
    asyncio.run(scenario())


def test_slow_cpu_overflow_stops_instead_of_accumulating_audio():
    async def scenario():
        entered,finish=asyncio.Event(),asyncio.Event()
        class Slow(Provider):
            async def transcribe(self,pcm):entered.set();await finish.wait();return "Late"
        async def send(v):pass
        s=CaptionSession(Slow);await s.connect("recruiter",send);await s.connect("candidate",send)
        await s.approve("recruiter");await s.approve("candidate")
        for _ in range(39):await s.audio("candidate",bytes(3200))
        task=asyncio.create_task(s.audio("candidate",bytes(3200)));await entered.wait()
        for _ in range(41):await s.audio("candidate",bytes(3200))
        assert s.stopped and not s.buffers["candidate"]
        finish.set();await task
    asyncio.run(scenario())


@pytest.mark.parametrize("origin,path",[("https://foreign.test","/api/v1/interview-access/captions"),
    ("http://localhost:5173","/api/v1/interview-access/captions?token=private")])
def test_socket_rejects_foreign_origin_or_secret_query_before_authorization(monkeypatch,origin,path):
    monkeypatch.setattr(route,"settings",route.settings.model_copy(update={"local_caption_model_path":"synthetic", "livekit_synthetic_demo_enabled":True}))
    async def forbidden(*args):pytest.fail("Must not authorize untrusted socket")
    monkeypatch.setattr(route,"authorize",forbidden)
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(path,headers={"origin":origin}):pass


def test_real_websocket_early_audio_fails_consent_gate(monkeypatch):
    monkeypatch.setattr(route,"settings",route.settings.model_copy(update={"local_caption_model_path":"synthetic", "livekit_synthetic_demo_enabled":True}))
    async def authorized(*args):return uuid4(),"candidate",uuid4(),datetime.now(timezone.utc)+timedelta(minutes=10)
    monkeypatch.setattr(route,"authorize",authorized)
    with TestClient(app) as client:
        with client.websocket_connect("/api/v1/interview-access/captions",headers={"origin":"http://localhost:5173"}) as socket:
            assert socket.receive_json()=={"kind":"waiting"}
            socket.send_bytes(bytes(3200));assert socket.receive_json()=={"kind":"stopped"}
    assert not route.sessions


def test_unauthorized_socket_never_creates_provider(monkeypatch):
    from fastapi import HTTPException
    monkeypatch.setattr(route,"settings",route.settings.model_copy(update={"local_caption_model_path":"synthetic", "livekit_synthetic_demo_enabled":True}))
    async def denied(*args):raise HTTPException(401,"PRIVATE")
    monkeypatch.setattr(route,"authorize",denied)
    with TestClient(app) as client, pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/v1/interview-access/captions",headers={"origin":"http://localhost:5173"}):pass
    assert not route.sessions


def test_worker_is_killed_on_cancellation_without_logging_audio(monkeypatch,tmp_path):
    import json
    from types import SimpleNamespace
    async def scenario():
        (tmp_path/"model.bin").touch()
        events=[]
        async def readline():return json.dumps({"ready":True}).encode()+b"\n"
        async def wait():events.append("wait")
        async def spawn(*args,**kwargs):
            assert "local_whisper_worker" in args[2]
            assert kwargs["stderr"]==asyncio.subprocess.DEVNULL
            return SimpleNamespace(stdout=SimpleNamespace(readline=readline),returncode=None,
                kill=lambda:events.append("kill"),wait=wait)
        monkeypatch.setattr(asyncio,"create_subprocess_exec",spawn)
        worker=LocalWhisper(tmp_path);await worker.start();await worker.close()
        assert events==["kill","wait"] and worker.process is None
    asyncio.run(scenario())


@pytest.mark.parametrize("withdraw", [False, True])
def test_pending_chunk_recovers_from_inference_delay_and_is_cleared_on_withdrawal(withdraw):
    async def scenario():
        entered, finish = asyncio.Event(), asyncio.Event()
        events = []
        class Delayed(Provider):
            async def transcribe(self, pcm):
                self.frames.append(pcm)
                if len(self.frames) == 1:
                    entered.set()
                    await finish.wait()
                return "Synthetic caption"
        async def send(value): events.append(value)
        s = CaptionSession(Delayed)
        await s.connect("recruiter", send)
        await s.connect("candidate", send)
        await s.approve("recruiter")
        await s.approve("candidate")
        provider = s.providers["candidate"]
        for _ in range(39): await s.audio("candidate", bytes(3200))
        task = asyncio.create_task(s.audio("candidate", bytes(3200)))
        await entered.wait()
        for _ in range(40): await s.audio("candidate", bytes(3200))
        assert not s.stopped and len(s.buffers["candidate"]) == 128000
        if withdraw: await s.stop()
        finish.set()
        await task
        assert len(provider.frames) == (1 if withdraw else 2)
        captions = [e for e in events if e["kind"] == "caption"]
        assert len(captions) == (0 if withdraw else 4)  # Two peer broadcasts.
        assert not s.buffers["candidate"]
        await s.stop()
    asyncio.run(scenario())


def test_worker_uses_one_offline_cpu_decoding_pass(monkeypatch):
    import io
    import json
    import struct
    import sys
    from types import SimpleNamespace
    from app.integrations.stt import local_whisper_worker
    calls = []
    class Samples:
        def astype(self, dtype): return self
        def __truediv__(self, value): return self
    class Model:
        def __init__(self, path, **options):
            assert options == dict(device="cpu", compute_type="int8", local_files_only=True, cpu_threads=2, num_workers=1)
        def transcribe(self, samples, **options):
            calls.append(options)
            return iter([SimpleNamespace(text="Synthetic caption")]), None
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=Model))
    monkeypatch.setitem(sys.modules, "numpy", SimpleNamespace(frombuffer=lambda *a, **k: Samples(), float32="float32"))
    monkeypatch.setattr(sys, "argv", ["worker", "synthetic-model"])
    monkeypatch.setattr(sys, "stdin", SimpleNamespace(buffer=io.BytesIO(struct.pack("!I", 128000)+bytes(128000))))
    output=io.StringIO();monkeypatch.setattr(sys, "stdout", output)
    local_whisper_worker.main()
    assert len(calls)==1 and calls[0]["temperature"]==0.0
    assert calls[0]["beam_size"]==1 and calls[0]["vad_filter"] is True
    assert calls[0]["condition_on_previous_text"] is False
    assert [json.loads(line) for line in output.getvalue().splitlines()]==[{"ready":True},{"text":"Synthetic caption"}]


def test_sustained_two_role_audio_has_bounded_memory_and_exact_caption_accounting():
    async def scenario():
        now=[0.0];events=[]
        async def send(value): events.append(value)
        s=CaptionSession(Provider, clock=lambda:now[0])
        await s.connect("recruiter",send);await s.connect("candidate",send)
        await s.approve("recruiter");await s.approve("candidate")
        for frame in range(1200):
            now[0]=frame/10
            # Independent roles, occasional grouped delivery; preserve every frame.
            await asyncio.gather(s.audio("recruiter",bytes(3200)),s.audio("candidate",bytes(3200)))
            assert all(len(buffer)<=128000 for buffer in s.buffers.values())
        assert not s.stopped and s.sequence==60
        assert s.frames==dict(recruiter=1200,candidate=1200)
        assert all(len(p.frames)==30 for p in s.providers.values())
        assert {e["role"] for e in events if e["kind"]=="caption"}=={"recruiter","candidate"}
        now[0]=120;await s.audio("recruiter",bytes(3200))
        assert s.stopped and not any(s.buffers.values())
    asyncio.run(scenario())


def test_websocket_burst_dispatch_does_not_mistake_fast_frames_for_backlog(monkeypatch):
    key=uuid4()
    monkeypatch.setattr(route,"settings",route.settings.model_copy(update={"local_caption_model_path":"synthetic", "livekit_synthetic_demo_enabled":True}))
    # Keep repeated authorization identity stable.
    identity=uuid4()
    expiry=datetime.now(timezone.utc)+timedelta(minutes=10)
    async def authorized(*args):return key,"candidate",identity,expiry
    monkeypatch.setattr(route,"authorize",authorized)
    async def send(value):pass
    session=CaptionSession(Provider)
    asyncio.run(session.connect("recruiter",send))
    session.consent.add("recruiter")
    route.sessions[key]=session
    try:
        with TestClient(app) as client:
            with client.websocket_connect("/api/v1/interview-access/captions",headers={"origin":"http://localhost:5173"}) as socket:
                assert socket.receive_json()["kind"]=="waiting"
                socket.send_text("consent");assert socket.receive_json()["kind"]=="active"
                for i in range(40):
                    socket.send_bytes(bytes(3200))
                    if i==19:
                        import time
                        time.sleep(1.05)
                assert socket.receive_json()["kind"]=="caption"
                assert not session.stopped and session.frames["candidate"]==40
                socket.send_text("stop");assert socket.receive_json()["kind"]=="stopped"
    finally: route.sessions.clear()


@pytest.mark.parametrize("withdraw",[False,True])
def test_bounded_four_second_batch_recovers_without_loss(withdraw):
    async def scenario():
        entered,release=asyncio.Event(),asyncio.Event();now=[0.];events=[]
        class Spike(Provider):
            async def transcribe(self,pcm):
                self.frames.append(pcm)
                if len(self.frames)==1:entered.set();await release.wait()
                return "Synthetic caption"
        async def send(value):events.append(value)
        s=CaptionSession(Spike,clock=lambda:now[0]);await s.connect("recruiter",send);await s.connect("candidate",send)
        await s.approve("recruiter");await s.approve("candidate");p=s.providers["candidate"]
        for i in range(39):now[0]=(i+1)/10;await s.audio("candidate",bytes(3200))
        now[0]=4.;task=asyncio.create_task(s.audio("candidate",bytes(3200)));await entered.wait()
        for i in range(40):now[0]=4.1+i/10;await s.audio("candidate",bytes(3200))
        assert not s.stopped and len(s.buffers["candidate"])==128000
        assert len(s.buffer_times["candidate"])==40
        if withdraw:await s.stop()
        release.set();await task
        assert len(p.frames)==(1 if withdraw else 2)
        assert all(len(frame)==128000 for frame in p.frames)
        assert not s.buffers["candidate"] and not s.buffer_times["candidate"]
        if not withdraw:
            captions=[e for e in events if e["kind"]=="caption"]
            assert [round(c["end"]) for c in captions[::2]]==[4,8]
        await s.stop()
    asyncio.run(scenario())


def test_whisper_pipe_accepts_exact_four_second_chunk_and_rejects_larger_audio(tmp_path):
    import struct
    from types import SimpleNamespace
    async def scenario():
        writes=[]
        async def drain():pass
        async def read():return b'{"text":"Synthetic caption"}\n'
        worker=LocalWhisper(tmp_path)
        worker.process=SimpleNamespace(stdin=SimpleNamespace(write=writes.append,drain=drain),stdout=SimpleNamespace(readline=read))
        assert await worker.transcribe(bytes(128000))=="Synthetic caption"
        assert struct.unpack("!I",writes[0][:4])[0]==128000
        for size in [0,128001,128002]:
            with pytest.raises(ValueError):await worker.transcribe(bytes(size))
        assert len(writes)==1
    asyncio.run(scenario())


def test_extended_duration_requires_synthetic_development_and_is_bounded():
    from app.core.config import Settings, ConfigurationError
    from pydantic import ValidationError
    base=dict(_env_file=None, database_url=None, langgraph_checkpoint_database_url=None)
    assert Settings(**base).local_caption_test_duration_seconds == 120
    assert Settings(**base,livekit_synthetic_demo_enabled=True,local_caption_test_duration_seconds=300).local_caption_test_duration_seconds==300
    for environment,enabled in [('production',True),('development',False)]:
        with pytest.raises(ConfigurationError):
            Settings(**base,environment=environment,livekit_synthetic_demo_enabled=enabled,local_caption_test_duration_seconds=300)
    for value in [119,301]:
        with pytest.raises(ValidationError):Settings(**base,local_caption_test_duration_seconds=value)


@pytest.mark.parametrize('deadline',[None,140.0])
def test_five_minute_session_stops_at_earlier_authorization_deadline(deadline):
    async def scenario():
        now=[0.];events=[]
        async def send(v):events.append(v)
        s=CaptionSession(Provider,clock=lambda:now[0],duration_seconds=300,authorization_deadline=deadline)
        await s.connect('recruiter',send);await s.connect('candidate',send)
        await s.approve('recruiter');await s.approve('candidate')
        providers=list(s.providers.values())
        limit=int(deadline or 300)
        for frame in range(limit*10):
            now[0]=frame/10
            for role in ['recruiter','candidate']:await s.audio(role,bytes(3200))
            assert all(len(b)<=128000 for b in s.buffers.values())
        assert not s.stopped and s.sequence==limit//4*2
        now[0]=limit;await s.audio('recruiter',bytes(3200))
        assert s.stopped and not s.providers and not s.consent
        assert all(p.closed for p in providers) and not any(s.buffer_times.values())
        with pytest.raises(ValueError):await s.audio('candidate',bytes(3200))
        fresh=CaptionSession(Provider,clock=lambda:now[0],duration_seconds=300,authorization_deadline=deadline)
        await fresh.connect('recruiter',send);await fresh.connect('candidate',send)
        await fresh.approve('recruiter')
        if deadline is not None:assert fresh.stopped
        else:assert not fresh.started and not fresh.providers  # reconnect requires both new consents
        await fresh.stop()
    asyncio.run(scenario())


def test_expiry_during_extended_decode_suppresses_late_caption_and_closes_workers():
    async def scenario():
        now=[0.];entered=asyncio.Event();release=asyncio.Event();events=[]
        class Slow(Provider):
            async def transcribe(self,pcm):entered.set();await release.wait();return 'Late synthetic caption'
        async def send(v):events.append(v)
        s=CaptionSession(Slow,clock=lambda:now[0],duration_seconds=300,authorization_deadline=5)
        await s.connect('recruiter',send);await s.connect('candidate',send)
        await s.approve('recruiter');await s.approve('candidate');providers=list(s.providers.values())
        for _ in range(39):await s.audio('candidate',bytes(3200))
        task=asyncio.create_task(s.audio('candidate',bytes(3200)));await entered.wait()
        now[0]=5;release.set();await task
        assert s.stopped and all(p.closed for p in providers)
        assert not [e for e in events if e['kind']=='caption']
    asyncio.run(scenario())


@pytest.mark.parametrize('reason',['expiry','revocation'])
def test_extended_websocket_authorization_loss_closes_resources(monkeypatch,reason):
    key,identity=uuid4(),uuid4();calls=[]
    expiry=datetime.now(timezone.utc)+timedelta(seconds=.2 if reason=='expiry' else 600)
    monkeypatch.setattr(route,'settings',route.settings.model_copy(update={'local_caption_model_path':'synthetic','livekit_synthetic_demo_enabled':True,'local_caption_test_duration_seconds':300}))
    async def authorize(*args):
        calls.append(1)
        if reason=='revocation' and len(calls)>1:raise ValueError('Access revoked')
        return key,'candidate',identity,expiry
    monkeypatch.setattr(route,'authorize',authorize)
    async def send(v):pass
    session=CaptionSession(Provider,duration_seconds=300)
    asyncio.run(session.connect('recruiter',send));session.consent.add('recruiter');route.sessions[key]=session
    providers=[]
    try:
        with TestClient(app) as client:
            with client.websocket_connect('/api/v1/interview-access/captions',headers={'origin':'http://localhost:5173'}) as ws:
                assert ws.receive_json()['kind']=='waiting';ws.send_text('consent')
                assert ws.receive_json()['duration_seconds']==300;providers.extend(session.providers.values())
                assert ws.receive_json()['kind']=='stopped';assert session.stopped
                ws.send_text('stop')
        assert all(p.closed for p in providers) and not session.providers and not session.consent
        # The manually supplied recruiter peer has no real socket/finalizer.
        # Candidate cleanup must remove only its peer; the stopped session
        # remains until that recruiter disconnects (as in the real UI).
        assert set(session.peers)=={'recruiter'} and session.stopped
    finally:route.sessions.clear()
