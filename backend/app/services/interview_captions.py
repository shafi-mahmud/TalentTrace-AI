"""Single-worker, single-room two-party consent; no persistent state or transcript."""
import asyncio
import time

ROLES = {"recruiter", "candidate"}


class CaptionSession:
    def __init__(self, provider_factory, clock=time.monotonic):
        self.factory, self.clock = provider_factory, clock
        self.peers, self.consent, self.buffers, self.providers = {}, set(), {}, {}
        self.started = None
        self.created = self.clock()
        self.sequence = 0
        self.lock = asyncio.Lock()
        self.stopped = False
        self.processing = set()
        self.frames = {role: 0 for role in ROLES}

    async def connect(self, role, send):
        if role not in ROLES or role in self.peers or self.stopped:
            raise ValueError("Caption session unavailable")
        self.peers[role] = send
        self.buffers[role] = bytearray()

    async def broadcast(self, value):
        await asyncio.gather(*(asyncio.wait_for(send(value), 1) for send in self.peers.values()))

    async def approve(self, role):
        async with self.lock:
            if role not in self.peers or self.stopped:
                raise ValueError("Caption consent unavailable")
            self.consent.add(role)
            if self.consent == ROLES and self.started is None:
                try:
                    for name in ROLES:
                        provider = self.factory()
                        self.providers[name] = provider
                        await provider.start()
                        if self.stopped:
                            await provider.close()
                            raise ValueError("Consent withdrawn")
                    self.started = self.clock()
                    await self.broadcast({"kind": "active"})
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
        await asyncio.gather(*(p.close() for p in self.providers.values()), return_exceptions=True)
        self.providers.clear()
        await asyncio.gather(*(asyncio.wait_for(send({"kind": "stopped"}), 1) for send in self.peers.values()), return_exceptions=True)

    async def audio(self, role, pcm):
        if self.stopped or self.consent != ROLES or self.started is None:
            raise ValueError("Audio requires both consents")
        if self.clock() - self.started >= 120:
            await self.stop()
            return
        if role not in self.peers or len(pcm) != 3200:
            raise ValueError("Bounded PCM16 frame required")
        self.frames[role] += 1
        if self.frames[role] > 1200:
            await self.stop()
            return
        buffer = self.buffers[role]
        buffer.extend(pcm)
        if len(buffer) < 64000:
            return
        if role in self.processing:
            await self.stop()
            return
        audio = bytes(buffer)
        buffer.clear()
        end = self.clock() - self.started
        try:
            self.processing.add(role)
            text = await self.providers[role].transcribe(audio)
            if not self.stopped and text:
                if len(text) > 1000 or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in text):
                    raise ValueError("Unsafe caption")
                if self.sequence >= 120:
                    await self.stop()
                    return
                self.sequence += 1
                await self.broadcast({"kind": "caption", "role": role, "sequence": self.sequence,
                                      "start": max(0, end - 2), "end": end, "text": text})
        except Exception:
            await self.stop()
        finally:
            self.processing.discard(role)
