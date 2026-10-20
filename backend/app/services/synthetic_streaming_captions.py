"""Server-owned question/answer replay through the existing authorized caption bridge."""
import asyncio
import time
from app.services.interview_captions import CaptionSession, ROLES
from app.integrations.stt.assemblyai_synthetic import fixture_pcm

# Process-local budget: one explicit attempt per configured interview until restart.
ATTEMPTED = set()


class SyntheticStreamingCaptions(CaptionSession):
    def __init__(self, factory, interview):
        super().__init__(None)
        self.stream_factory = factory
        self.interview = interview
        self.replay = None
        self.complete = False

    async def approve(self, role):
        async with self.lock:
            if role not in self.peers or self.stopped or self.expired():
                raise ValueError('Synthetic consent unavailable')
            self.consent.add(role)
            if self.consent == ROLES and self.started is None:
                # No provider connection until explicit recruiter start after F11 consent.
                fixture_pcm('recruiter'); fixture_pcm('candidate')
                self.started, self.started_wall = self.clock(), time.time()
                await self.broadcast({'kind': 'active', 'duration_seconds': 120,
                                      'source': 'assemblyai-synthetic'})
            elif self.started is None:
                await self.broadcast({'kind': 'waiting'})

    async def start_replay(self, role):
        async with self.lock:
            if (role != 'recruiter' or self.stopped or self.expired() or self.consent != ROLES
                    or self.started is None or self.replay is not None or self.interview in ATTEMPTED):
                raise ValueError('Synthetic replay unavailable')
            await self._check_access()
            if (not self.assistant or self.assistant.manager.live_context(
                    self.interview, self.caption_run_id) is None):
                raise ValueError('Independent assistant consent required')
            self.assistant_context = self.assistant.manager.live_context(self.interview, self.caption_run_id)
            ATTEMPTED.add(self.interview)
            self.replay = asyncio.create_task(self._replay())

    async def _ensure_replay_access(self):
        if set(self.authorization_checks) != ROLES:
            raise ValueError('Both participant authorizations required')
        await asyncio.wait_for(self._check_access(), 2)
        if (self.stopped or self.expired() or self.consent != ROLES
                or self.assistant.manager.live_context(self.interview, self.caption_run_id)
                != self.assistant_context):
            raise ValueError('Synthetic replay authorization ended')

    async def _run_provider(self, provider):
        task = asyncio.create_task(provider.run())
        try:
            while not task.done():
                await asyncio.wait({task}, timeout=.25)
                await self._ensure_replay_access()
            return await task
        finally:
            if not task.done():
                await provider.close()
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _replay(self):
        try:
            # F11's cutoff is an audio-time boundary, not recognition-return time.
            cutoff = self.assistant_context[3]
            now_wall = self.started_wall + self.clock() - self.started
            if now_wall <= cutoff:
                await asyncio.sleep(cutoff - now_wall + .05)
            await self._ensure_replay_access()
            # Sequential sessions guarantee a complete recruiter question before candidate answer.
            for role in ('recruiter', 'candidate'):
                await self._ensure_replay_access()
                if self.stopped or self.expired() or self.consent != ROLES:
                    raise ValueError('Synthetic replay ended')
                provider = self.stream_factory(role)
                self.providers[role] = provider
                text = await self._run_provider(provider)
                await self._ensure_replay_access()
                if self.stopped or self.expired() or self.consent != ROLES:
                    raise ValueError('Late synthetic final')
                samples = len(fixture_pcm(role)) // 2
                self.accepted_samples[role] = self.processed_samples[role] = samples
                self.frames[role] = (samples + 1599) // 1600
                await self._publish_caption(role, text, provider.audio_started_at - self.started,
                                            provider.audio_ended_at - self.started)
            self.complete = True
            await self.broadcast({'kind': 'synthetic-complete'})
            # Keep the authorized bridge alive for settling/recruiter review; streams are closed.
        except asyncio.CancelledError:
            raise
        except Exception:
            # Fixed status only; never expose provider exception/credential bodies.
            asyncio.create_task(self.stop())

    async def audio(self, role, pcm):
        raise ValueError('Browser audio forbidden in server-owned synthetic replay')

    async def end_audio(self, role, value):
        raise ValueError('Browser audio accounting forbidden in synthetic replay')

    async def request_finish(self, role):
        if self.stopped or role not in self.peers or self.consent != ROLES:
            raise ValueError('Synthetic finish unavailable')
        if self.finishing:
            return
        self.finishing = True
        await self.broadcast({'kind': 'synthetic-finishing'})
        async def finish():
            try:
                if self.replay:
                    await asyncio.wait_for(asyncio.shield(self.replay), 35)
            finally:
                self.final_result = self.summary('drained' if self.complete else 'partial')
                await self.stop()
        self.finalizer = asyncio.create_task(finish())

    async def _cleanup(self):
        for provider in self.providers.values():
            await provider.close()  # Fence output before awaiting stream termination.
        if self.replay and not self.replay.done():
            self.replay.cancel()
        if self.replay:
            await asyncio.gather(self.replay, return_exceptions=True)
        try:
            await self.broadcast({'kind': 'synthetic-termination', 'confirmed': all(
                getattr(p, 'termination_confirmed', False) for p in self.providers.values()),
                'sessions': len(self.providers)})
        except Exception:
            pass  # A disconnected browser must not interrupt provider cleanup.
        await super()._cleanup()
