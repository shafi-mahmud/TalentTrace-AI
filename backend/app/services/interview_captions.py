"""Single-worker, single-room two-party consent; no persistent state or transcript."""
import asyncio
import time
from collections import deque
from app.integrations.stt.local_whisper import MAX_CHUNK_BYTES

ROLES = {"recruiter", "candidate"}
CHUNK_BYTES = MAX_CHUNK_BYTES
MAX_PENDING_BYTES = CHUNK_BYTES  # Pending bound stays four seconds per role.


class CaptionSession:
    def __init__(self, provider_factory, clock=time.monotonic, duration_seconds=120, authorization_deadline=None):
        if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or not 120 <= duration_seconds <= 300:
            raise ValueError("Bounded caption duration required")
        self.duration_seconds = duration_seconds
        self.authorization_deadline = authorization_deadline
        self.factory, self.clock = provider_factory, clock
        self.peers, self.consent, self.buffers, self.providers = {}, set(), {}, {}
        self.started = None
        self.created = self.clock()
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.stopped = False
        self.processing = set()
        self.buffer_times = {}
        self.frames = {role: 0 for role in ROLES}

    def expired(self):
        now = self.clock()
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
                    self.started = self.clock()
                    await self.broadcast({"kind": "active", "duration_seconds": self.duration_seconds})
                except Exception:
                    await self.stop()
            elif self.started is None:
                await self.broadcast({"kind": "waiting"})

    async def stop(self):
        # Close the consent gate synchronously before awaiting cleanup.
        self.stopped = True
        self.consent.clear()
        for buffer in self.buffers.values():
            buffer.clear()
        for timestamps in self.buffer_times.values():
            timestamps.clear()
        await asyncio.gather(*(p.close() for p in self.providers.values()), return_exceptions=True)
        self.providers.clear()
        await asyncio.gather(*(asyncio.wait_for(send({"kind": "stopped"}), 1) for send in self.peers.values()), return_exceptions=True)

    async def audio(self, role, pcm):
        if self.stopped or self.consent != ROLES or self.started is None:
            raise ValueError("Audio requires both consents")
        if self.expired():
            await self.stop()
            return
        if role not in self.peers or len(pcm) != 3200:
            raise ValueError("Bounded PCM16 frame required")
        self.frames[role] += 1
        if self.frames[role] > self.duration_seconds * 10:
            await self.stop()
            return
        buffer = self.buffers[role]
        buffer.extend(pcm)
        self.buffer_times[role].append(self.clock() - self.started)
        # Four-second batching amortizes measured inference overhead. Keep only
        # one pending chunk and fail closed when this fixed capacity is exceeded.
        if len(buffer) > MAX_PENDING_BYTES:
            await self.stop()
            return
        if len(buffer) < CHUNK_BYTES or role in self.processing:
            return
        try:
            self.processing.add(role)
            while not self.stopped and len(buffer) >= CHUNK_BYTES:
                if self.expired():
                    await self.stop()
                    return
                timestamps = [self.buffer_times[role].popleft() for _ in range(CHUNK_BYTES // 3200)]
                start, end = max(0, timestamps[0] - 0.1), timestamps[-1]
                audio = bytes(buffer[:CHUNK_BYTES])
                del buffer[:CHUNK_BYTES]
                text = await self.providers[role].transcribe(audio)
                if self.expired():
                    await self.stop()
                    return
                if not self.stopped and text:
                    if len(text) > 1000 or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in text):
                        raise ValueError("Unsafe caption")
                    if self.sequence >= max(120, self.duration_seconds // 2):
                        await self.stop()
                        return
                    self.sequence += 1
                    await self.broadcast({"kind": "caption", "role": role, "sequence": self.sequence,
                                          "start": start, "end": end, "text": text})
        except Exception:
            await self.stop()
        finally:
            self.processing.discard(role)
