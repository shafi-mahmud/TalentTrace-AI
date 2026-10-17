"""Bounded privacy maintenance independent of confirmation/transcript serving flags."""
import asyncio
from app.core.auth import session_factory
from app.core.config import settings
from app.services.reviewer_confirmation import sweep_confirmations

maintenance_status = {'state':'not_started'}


async def maintenance_loop():
    while True:
        try:
            async with session_factory().begin() as db:
                await sweep_confirmations(db)
            maintenance_status['state']='running'
        except Exception:
            maintenance_status['state']='unavailable'  # No SQL, credentials or content.
        await asyncio.sleep(settings.transcript_cleanup_interval_seconds)
