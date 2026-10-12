"""Short-lived synthetic room grants; never persist or log tokens/credentials."""
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from uuid import UUID

from app.core.config import settings

TOKEN_TTL_SECONDS = 300


class LiveKitUnavailable(RuntimeError):
    pass


def livekit_configuration():
    if settings.environment != "development" or not settings.livekit_synthetic_demo_enabled:
        raise LiveKitUnavailable()
    if not all((settings.livekit_url, settings.livekit_api_key, settings.livekit_api_secret)):
        raise LiveKitUnavailable()
    url = settings.livekit_url.get_secret_value()
    parsed = urlsplit(url)
    if (parsed.scheme != "wss" or not parsed.hostname or not parsed.hostname.endswith(".livekit.cloud")
        or parsed.username or parsed.password or parsed.port not in {None, 443}
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment):
        raise LiveKitUnavailable()
    key = settings.livekit_api_key.get_secret_value()
    secret = settings.livekit_api_secret.get_secret_value()
    if not key.strip() or not secret.strip():
        raise LiveKitUnavailable()
    return url, key, secret


def room_identity(interview_id: UUID, participant_id: UUID, role: str):
    if role not in {"recruiter", "candidate"}:
        raise LiveKitUnavailable()
    _, _, secret = livekit_configuration()
    def opaque(label):
        return hmac.new(secret.encode(), label.encode(), hashlib.sha256).hexdigest()[:32]
    room = "tt-room-" + opaque(f"room:{interview_id}")
    participant = "tt-participant-" + opaque(f"participant:{interview_id}:{participant_id}:{role}")
    return room, participant


def join_window(interview, now=None):
    """Ten minutes before until fifteen minutes after the scheduled duration."""
    now = now or datetime.now(timezone.utc)
    end = interview.scheduled_at + timedelta(minutes=interview.duration_minutes + 15)
    if now < interview.scheduled_at - timedelta(minutes=10) or now >= end:
        raise ValueError("Interview join window is closed.")
    return max(1, min(TOKEN_TTL_SECONDS, int((end - now).total_seconds())))


def issue_interview_token(interview_id: UUID, participant_id: UUID, role: str, ttl=TOKEN_TTL_SECONDS):
    if not 1 <= ttl <= TOKEN_TTL_SECONDS:
        raise LiveKitUnavailable()
    url, key, secret = livekit_configuration()
    room, participant = room_identity(interview_id, participant_id, role)
    from livekit import api
    token = (api.AccessToken(key, secret).with_identity(participant)
        .with_ttl(timedelta(seconds=ttl)).with_grants(api.VideoGrants(
            room_join=True, room=room, room_create=False, room_list=False, room_admin=False,
            room_record=False, can_publish=True, can_subscribe=True, can_publish_data=False,
            can_update_own_metadata=False, can_publish_sources=["camera", "microphone"])).to_jwt())
    return {"server_url": url, "token": token, "expires_in": ttl}


async def revoke_candidate_access(interview_id, invitation_id):
    """Cloud removal revokes cached tokens as well as the active connection."""
    from livekit import api
    import time
    url, key, secret = livekit_configuration()
    room, identity = room_identity(interview_id, invitation_id, "candidate")
    async with api.LiveKitAPI(url=url.replace("wss://", "https://", 1), api_key=key, api_secret=secret) as client:
        await client.room.remove_participant(api.RoomParticipantIdentity(
            room=room, identity=identity, revoke_token_ts=int(time.time()) + 1))
