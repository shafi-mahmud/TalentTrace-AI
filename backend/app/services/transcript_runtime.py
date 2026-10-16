"""Explicitly enabled singleton for the existing single-room caption worker."""
import asyncio
from functools import lru_cache
from types import SimpleNamespace
from app.core.auth import session_factory
from app.core.config import settings
from app.services.interview_transcripts import StorageConsentAuthority, TranscriptPersistenceService, TranscriptError
from app.services.transcript_consent import TranscriptConsentCoordinator, CONSENT_VERSION
from app.services.transcript_privacy import TranscriptPrivacyService

maintenance_status = {'state': 'not_started', 'processed': 0, 'failed': 0}


@lru_cache(maxsize=1)
def runtime():
    if not settings.transcript_storage_enabled:
        raise TranscriptError('transcript_storage_disabled')
    authority = StorageConsentAuthority(session_factory(), version=CONSENT_VERSION)
    storage = TranscriptPersistenceService(authority.factory, authority)
    return SimpleNamespace(authority=authority, storage=storage,
        privacy=TranscriptPrivacyService(storage), coordinator=TranscriptConsentCoordinator(authority, storage))


async def maintenance_loop():
    while True:
        try:
            result = await runtime().privacy.sweep()
            maintenance_status.update(state='running', **result)
        except Exception:
            # Fixed operational status only. Never log exception/SQL/content.
            maintenance_status.update(state='unavailable', failed=1)
        await asyncio.sleep(settings.transcript_cleanup_interval_seconds)
