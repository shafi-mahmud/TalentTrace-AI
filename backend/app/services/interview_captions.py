"""Single-worker, single-room two-party consent; no persistent state or transcript."""
import asyncio
import time
from collections import deque
from uuid import uuid4
from app.integrations.stt.local_whisper import MAX_CHUNK_BYTES

ROLES = {"recruiter", "candidate"}
CHUNK_BYTES = MAX_CHUNK_BYTES
MAX_PENDING_BYTES = CHUNK_BYTES  # Pending bound stays four seconds per role.
FINALIZATION_SECONDS = 35


class CaptionSession:
    def __init__(self, provider_factory, clock=time.monotonic, duration_seconds=120, authorization_deadline=None, storage=None):
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not 120 <= duration_seconds <= 300:
            raise ValueError("Bounded caption duration required")
        self.caption_run_id = uuid4()
        self.started_wall = None
        self.assistant = None
        self.assistant_access = None
        self.duration_seconds = duration_seconds
        self.authorization_deadline = authorization_deadline
        self.factory, self.clock = provider_factory, clock
        self.storage = storage
        self.drain_deadline = None
        self.peers, self.consent, self.buffers, self.providers = {}, set(), {}, {}
        self.started = None
        self.created = self.clock()
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.stopped = False
        self.processing = set()
        self.buffer_times = {}
        self.frames = {role: 0 for role in ROLES}
        self.accepted_samples = {role: 0 for role in ROLES}
        self.processed_samples = {role: 0 for role in ROLES}
        self.caption_events = {role: 0 for role in ROLES}
        self.ends = {}
        self.tail_roles = set()
        self.finishing = False
        self.finalizer = None
        self.final_result = None
        self.cleanup_task = None
        self.authorization_checks = {}
        self.ended = asyncio.Event()
        self.idle = {role: asyncio.Event() for role in ROLES}
        for idle in self.idle.values(): idle.set()

    def expired(self):
        now = self.clock()
        if self.finishing and self.drain_deadline is not None:
            return now >= self.drain_deadline
        return ((self.authorization_deadline is not None and now >= self.authorization_deadline)
                or (self.started is not None and now - self.started >= self.duration_seconds))

    async def connect(self, role, send):
        if role not in ROLES or role in self.peers or self.stopped:
            raise ValueError("Caption session unavailable")
        self.peers[role] = send
        self.buffers[role] = bytearray()
        self.buffer_times[role] = deque()

    async def broadcast(self, value):
        await asyncio.gather(*(asyncio.wait_for(send(value), 1) for send in self.peers.values()))

    async def approve(self, role):
        async with self.lock:
            if role not in self.peers or self.stopped:
                raise ValueError("Caption consent unavailable")
            if self.expired():
                await self.stop()
                return
            self.consent.add(role)
            if self.consent == ROLES and self.started is None:
                try:
                    for name in ROLES:
                        provider = self.factory()
                        self.providers[name] = provider
                        await provider.start()
                        if self.stopped or self.expired():
                            await provider.close()
                            raise ValueError("Consent withdrawn")
                    if self.storage:
                        await self.storage.start()
                    self.started = self.clock()
                    self.started_wall = time.time()
                    await self.broadcast({"kind": "active", "duration_seconds": self.duration_seconds})
                except Exception:
                    await self.stop()
            elif self.started is None:
                await self.broadcast({"kind": "waiting"})

    async def stop(self):
        # Close the consent gate synchronously before awaiting cleanup.
        if self.stopped:
            if self.cleanup_task:
                await asyncio.shield(self.cleanup_task)
            return
        self.stopped = True
        self._close_assistant()
        self.consent.clear()
        for buffer in self.buffers.values():
            buffer.clear()
        for timestamps in self.buffer_times.values():
            timestamps.clear()
        self.cleanup_task = asyncio.create_task(self._cleanup())
        if self.finalizer and self.finalizer is not asyncio.current_task():
            self.finalizer.cancel()
        await asyncio.shield(self.cleanup_task)

    def _close_assistant(self):
        if self.assistant:
            try:
                self.assistant.close()
            except Exception:
                pass  # Optional assistant cannot break captions or finalization.

    async def _cleanup(self):
        await asyncio.gather(*(asyncio.wait_for(p.close(), 2) for p in self.providers.values()), return_exceptions=True)
        self.providers.clear()
        if self.storage:
            try:
                result = await asyncio.wait_for(self.storage.finish(self.final_result or self.summary('partial' if any(self.processed_samples.values()) else 'failed')), 5)
                await asyncio.gather(*(asyncio.wait_for(send(result), 1) for send in self.peers.values()), return_exceptions=True)
            except Exception:
                await asyncio.gather(*(asyncio.wait_for(send({'kind':'storage','status':'unconfirmed','committed_turns':0}),1) for send in self.peers.values()),return_exceptions=True)
        if self.finishing and self.final_result is None:
            self.final_result = self.summary('partial' if any(self.processed_samples.values()) else 'failed')
            await asyncio.gather(*(asyncio.wait_for(send(self.final_result), 1) for send in self.peers.values()), return_exceptions=True)
        await asyncio.gather(*(asyncio.wait_for(send({"kind": "stopped"}), 1) for send in self.peers.values()), return_exceptions=True)

    def summary(self, outcome):
        return {"kind": "finalized", "outcome": outcome, "roles": {
            role: {"accepted_frames": self.frames[role], "accepted_samples": self.accepted_samples[role],
                   "processed_samples": self.processed_samples[role], "caption_events": self.caption_events[role],
                   "captured_samples": self.ends.get(role, {}).get('captured_samples')}
            for role in sorted(ROLES)}}

    async def request_finish(self, role):
        if self.stopped or role not in self.peers or self.started is None or self.consent != ROLES or self.expired():
            raise ValueError('Normal finalization unavailable')
        if self.finishing:
            return
        self._close_assistant()
        if self.storage:
            await self.storage.begin_finish()
            if self.storage.grace_until is not None:
                self.drain_deadline = self.clock() + FINALIZATION_SECONDS
        self.finishing = True
        self.finalizer = asyncio.create_task(self._finalize())
        await self.broadcast({"kind": "finishing", "deadline_seconds": FINALIZATION_SECONDS})

    async def end_audio(self, role, value):
        if not self.finishing or self.stopped or role not in self.peers:
            raise ValueError('Unexpected audio end')
        if set(value) != {'kind', 'frames', 'samples', 'captured_samples'} or value['kind'] != 'end':
            raise ValueError('Invalid audio end')
        if any(type(value[k]) is not int or value[k] < 0 for k in ('frames','samples','captured_samples')):
            raise ValueError('Invalid audio accounting')
        if (value['frames'] != self.frames[role] or value['samples'] != self.accepted_samples[role]
                or not value['samples'] <= value['captured_samples'] <= self.duration_seconds * 16000):
            raise ValueError('Audio accounting mismatch')
        if role in self.ends and self.ends[role] != value:
            raise ValueError('Conflicting audio end')
        self.ends[role] = dict(value)
        await asyncio.wait_for(self.peers[role]({"kind":"accepted", "frames":self.frames[role], "samples":self.accepted_samples[role]}), 1)
        if set(self.ends) == ROLES:
            self.ended.set()

    async def _finalize(self):
        try:
            async with asyncio.timeout(FINALIZATION_SECONDS):
                await self.ended.wait()
                await asyncio.gather(*(idle.wait() for idle in self.idle.values()))
                if self.stopped or self.expired():
                    await self.stop()
                    return
                # Separate role workers drain concurrently, never concurrently per role.
                await asyncio.gather(*(self._drain_tail(role) for role in ROLES))
                await self._check_access()
                if self.stopped or self.expired():
                    await self.stop()
                    return
                if self.accepted_samples != self.processed_samples:
                    raise ValueError('Audio drain incomplete')
                result = self.summary('drained')
                self.final_result = result
                await self.broadcast(result)
                await self.stop()
        except asyncio.CancelledError:
            raise
        except Exception:
            await self.stop()

    async def _check_access(self):
        if self.authorization_checks:
            if set(self.authorization_checks) != ROLES:
                raise ValueError('Final authorization unavailable')
            await asyncio.gather(*(check() for check in self.authorization_checks.values()))

    async def _decode(self, role, audio, start, end):
        text = await self.providers[role].transcribe(audio)
        if self.finishing:
            await self._check_access()
        await self._publish_caption(role, text, start, end, samples=len(audio) // 2)

    async def _publish_caption(self, role, text, start, end, *, samples=0):
        """Shared event envelope; streaming sessions supply finalized text only."""
        if self.stopped:
            return
        if self.expired():
            await self.stop()
            return
        if not isinstance(text, str) or len(text) > 1000 or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in text):
            raise ValueError('Unsafe caption')
        self.processed_samples[role] += samples
        if text:
            # One extra tail event per role; legacy caption fields stay unchanged.
            if self.sequence >= max(120, self.duration_seconds // 2):
                raise ValueError('Caption limit exceeded')
            self.sequence += 1
            event = {"kind":"caption", "role":role, "sequence":self.sequence,
                     "start":start, "end":end, "text":text}
            if self.assistant:
                try:
                    self.assistant.offer(self.caption_run_id, self.started_wall, event)
                except Exception:
                    self._close_assistant()
            await self.broadcast(event)
            self.caption_events[role] += 1
            if self.storage:
                await self.storage.caption(event)

    async def _drain_tail(self, role):
        buffer = self.buffers[role]
        if not buffer or self.stopped:
            return
        intervals = list(self.buffer_times[role]); self.buffer_times[role].clear()
        audio = bytes(buffer); buffer.clear()
        await self._decode(role, audio, intervals[0][0], intervals[-1][1])

    async def audio(self, role, pcm):
        if self.stopped or self.consent != ROLES or self.started is None:
            raise ValueError("Audio requires both consents")
        if self.expired():
            await self.stop()
            return
        if (role not in self.peers or role in self.ends or role in self.tail_roles or not 0 < len(pcm) <= 3200 or len(pcm) % 2
                or (len(pcm) != 3200 and not self.finishing)):
            raise ValueError("Bounded PCM16 frame required")
        if self.accepted_samples[role] + len(pcm) // 2 > self.duration_seconds * 16000:
            await self.stop()
            return
        buffer = self.buffers[role]
        # Four-second batching amortizes measured inference overhead. Keep only
        # one pending chunk and fail closed when this fixed capacity is exceeded.
        if len(buffer) + len(pcm) > MAX_PENDING_BYTES:
            await self.stop()
            return
        self.frames[role] += 1
        if len(pcm) != 3200:
            self.tail_roles.add(role)
        self.accepted_samples[role] += len(pcm) // 2
        buffer.extend(pcm)
        end = self.clock() - self.started
        self.buffer_times[role].append((max(0, end - len(pcm) / 32000), end))
        if len(buffer) < CHUNK_BYTES or role in self.processing:
            return
        try:
            self.processing.add(role)
            self.idle[role].clear()
            while not self.stopped and len(buffer) >= CHUNK_BYTES:
                if self.expired():
                    await self.stop()
                    return
                timestamps = [self.buffer_times[role].popleft() for _ in range(CHUNK_BYTES // 3200)]
                start, end = timestamps[0][0], timestamps[-1][1]
                audio = bytes(buffer[:CHUNK_BYTES])
                del buffer[:CHUNK_BYTES]
                await self._decode(role, audio, start, end)
        except Exception:
            await self.stop()
        finally:
            self.processing.discard(role)
            self.idle[role].set()
