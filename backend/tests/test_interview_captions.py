"""Offline synthetic PCM/provider tests; no Cloud, microphone, model or DB call."""
import asyncio
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
            for _ in range(20): await session.audio(role, bytes(3200))
        captions=[e for e in events if e["kind"]=="caption"]
        assert {e["role"] for e in captions}=={"recruiter","candidate"}
        assert all(e["start"]<=e["end"] and e["sequence"]>0 for e in captions)
        assert all(len(p.frames)==1 and len(p.frames[0])==64000 for p in providers)
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
        for _ in range(19):await s.audio("candidate",bytes(3200))
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
        for _ in range(20):await s.audio("candidate",bytes(3200))
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
            for _ in range(20):await s.audio("candidate",bytes(3200))
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
        for _ in range(19):await s.audio("candidate",bytes(3200))
        task=asyncio.create_task(s.audio("candidate",bytes(3200)));await entered.wait()
        for _ in range(20):await s.audio("candidate",bytes(3200))
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
    async def authorized(*args):return uuid4(),"candidate",uuid4()
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
