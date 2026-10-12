"""Short-lived synthetic room grants; never persist or log tokens/credentials."""
import hashlib
import hmac
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

from app.core.config import settings

TOKEN_TTL_SECONDS = 300


class LiveKitUnavailable(RuntimeError):
    pass


def issue_interview_token(interview_id: UUID, recruiter_id: UUID, slot: str):
    if slot not in {"a", "b"} or settings.environment != "development" or not settings.livekit_synthetic_demo_enabled:
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
    # HMAC prevents opaque IDs from exposing database/recruiter identities.
    def opaque(label):
        return hmac.new(secret.encode(), label.encode(), hashlib.sha256).hexdigest()[:32]
    room = "tt-room-" + opaque(f"room:{interview_id}")
    participant = "tt-participant-" + opaque(f"participant:{interview_id}:{recruiter_id}:{slot}")
    from livekit import api
    token = (api.AccessToken(key, secret).with_identity(participant)
        .with_ttl(timedelta(seconds=TOKEN_TTL_SECONDS)).with_grants(api.VideoGrants(
            room_join=True, room=room, room_create=False, room_list=False, room_admin=False,
            room_record=False, can_publish=True, can_subscribe=True, can_publish_data=False,
            can_update_own_metadata=False, can_publish_sources=["camera", "microphone"])).to_jwt())
    return {"server_url": url, "token": token, "expires_in": TOKEN_TTL_SECONDS}
