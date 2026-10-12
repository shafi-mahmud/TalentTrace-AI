"""Authenticated temporary microphone bridge; never calls a cloud STT provider."""
import asyncio
from uuid import UUID

from fastapi import APIRouter, WebSocket
from starlette.requests import Request
from app.core.auth import current_recruiter, session_factory
from app.core.config import settings
from app.api.routers.interview_access import candidate_session, owned_schedule
from app.services.livekit_interview import join_window
from app.services.interview_captions import CaptionSession
from app.integrations.stt.local_whisper import LocalWhisper

router = APIRouter()
sessions = {}


def trusted_socket(socket):
    return (not socket.query_params and socket.headers.get("origin") in settings.cors_origins
            and settings.environment == "development" and settings.livekit_synthetic_demo_enabled
            and settings.local_caption_model_path is not None)


async def authorize(socket, job_id=None, interview_id=None):
    request = Request({**socket.scope, "type": "http", "method": "GET"})
    async with session_factory()() as db:
        if job_id is not None:
            user = await current_recruiter(request, db)
            interview = await owned_schedule(db, user, job_id, interview_id)
            identity, role = user.id, "recruiter"
        else:
            invitation, interview = await candidate_session(request, db)
            identity, role = invitation.id, "candidate"
        join_window(interview)
        return interview.id, role, identity


async def serve(socket, job_id=None, interview_id=None):
    if not trusted_socket(socket):
        await socket.close(code=1008)
        return
    session = None
    tasks = set()
    monitor = None
    try:
        association = await authorize(socket, job_id, interview_id)
        key, role, _ = association
        if key not in sessions:
            if sessions:  # Explicit single-room proof bound.
                raise ValueError("Caption capacity unavailable")
            sessions[key] = CaptionSession(lambda: LocalWhisper(settings.local_caption_model_path))
        session = sessions[key]
        await socket.accept()
        await session.connect(role, socket.send_json)
        await socket.send_json({"kind": "waiting"})

        async def watch():
            while not session.stopped:
                await asyncio.sleep(1)
                try:
                    if await authorize(socket, job_id, interview_id) != association:
                        raise ValueError("Access changed")
                    if session.started is not None and session.clock() - session.started >= 120:
                        raise ValueError("Caption window ended")
                    if session.started is None and session.clock() - session.created >= 120:
                        raise ValueError("Consent window ended")
                except Exception:
                    await session.stop()
                    return

        async def audio(pcm):
            try:
                await session.audio(role, pcm)
            except Exception:
                await session.stop()

        monitor = asyncio.create_task(watch())
        last_control = 0
        interval, messages = session.clock(), 0
        while not session.stopped:
            message = await asyncio.wait_for(socket.receive(), 5)
            now = session.clock()
            if now - interval >= 1:
                interval, messages = now, 0
            messages += 1
            if messages > 25:
                raise ValueError("Caption input rate exceeded")
            if message["type"] == "websocket.disconnect":
                break
            if message.get("bytes") is not None:
                if len(message["bytes"]) != 3200:
                    raise ValueError("Invalid PCM frame")
                tasks = {t for t in tasks if not t.done()}
                if len(tasks) >= 2:
                    raise ValueError("Audio overflow")
                tasks.add(asyncio.create_task(audio(message["bytes"])))
            elif message.get("text") == "stop":
                break
            elif message.get("text") == "consent":
                now = session.clock()
                if now - last_control < 1:
                    raise ValueError("Control rate exceeded")
                last_control = now
                await session.approve(role)
            elif message.get("text") != "ping":
                raise ValueError("Invalid control")
    except Exception:
        pass  # No exception body, audio, transcript, cookies or provider response logging.
    finally:
        if session and socket.send_json in session.peers.values():
            await session.stop()
            session.peers.pop(role, None)
            if not session.peers:
                sessions.pop(key, None)
        if monitor:
            monitor.cancel()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*(tasks | ({monitor} if monitor else set())), return_exceptions=True)
        try:
            await socket.close()
        except RuntimeError:
            pass


@router.websocket("/jobs/{job_id}/interviews/{interview_id}/captions")
async def recruiter_captions(socket: WebSocket, job_id: UUID, interview_id: UUID):
    await serve(socket, job_id, interview_id)


@router.websocket("/interview-access/captions")
async def candidate_captions(socket: WebSocket):
    await serve(socket)
