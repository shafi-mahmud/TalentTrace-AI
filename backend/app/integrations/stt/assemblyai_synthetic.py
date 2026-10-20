"""Bounded synthetic-only stream. Never accepts caller audio or arbitrary paths."""
import asyncio
import hashlib
import json
from pathlib import Path
import time
import wave

FIXTURES = Path(__file__).with_name('synthetic')
DIGESTS = {
    'recruiter': '05a476e9a916a620b9d697b0fe5f1624ec18f68556dddfa6aa0c289d9d43a524',
    'candidate': 'fbead5cbd83c351a1ef740eed57dacf53c198ebdcf6b56e45f628ef42af1930d',
}
URL = ('wss://streaming.assemblyai.com/v3/ws?sample_rate=16000&encoding=pcm_s16le'
       '&speech_model=universal-streaming-english&format_turns=true')


def fixture_pcm(role):
    if role not in DIGESTS:
        raise ValueError('Unknown synthetic role')
    path = FIXTURES / (role + '.wav')
    if hashlib.sha256(path.read_bytes()).hexdigest() != DIGESTS[role]:
        raise ValueError('Synthetic fixture integrity failure')
    with wave.open(str(path), 'rb') as audio:
        if (audio.getnchannels(), audio.getsampwidth(), audio.getframerate()) != (1, 2, 16000):
            raise ValueError('Synthetic fixture format failure')
        return audio.readframes(audio.getnframes())


async def connect(url, **kwargs):
    import websockets  # Optional STT requirements only; never imported on baseline startup.
    return await websockets.connect(url, **kwargs)


class AssemblyAISyntheticStream:
    """One role, one connection, no retry. Output available only after acknowledged termination."""
    def __init__(self, role, key, *, connector=connect, sleep=asyncio.sleep):
        self.role, self.key = role, key
        self.connector, self.sleep = connector, sleep
        self.ws = None
        self.reader = None
        self.closed = False
        self.attempted = False
        self.terminated = asyncio.Event()
        self.begun = asyncio.Event()
        self.finals = {}
        self.model = None
        self.termination_confirmed = False
        self.usage = None
        self.deadline = None
        self.terminate_sent = False
        self.audio_started_at = None
        self.audio_ended_at = None

    async def _receive(self):
        async for raw in self.ws:
            if not isinstance(raw, str) or len(raw) > 65536:
                raise ValueError('Invalid streaming message')
            value = json.loads(raw)
            kind = value.get('type')
            if kind == 'Begin':
                self.model = value.get('configuration', {}).get('model')
                if self.model and self.model != 'universal-streaming-english':
                    raise ValueError('Unexpected recognizer model')
                self.begun.set()
            elif (kind == 'Turn' and value.get('end_of_turn') is True
                  and value.get('turn_is_formatted') is True):
                order, text = value.get('turn_order'), value.get('transcript')
                if type(order) is not int or not 0 <= order < 30 or not isinstance(text, str):
                    raise ValueError('Invalid final turn')
                if len(text) > 1000 or any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in text):
                    raise ValueError('Invalid final text')
                if order in self.finals and self.finals[order] != text:
                    raise ValueError('Conflicting finalized turn')
                self.finals[order] = text
                if sum(map(len, self.finals.values())) > 1000:
                    raise ValueError('Unbounded final text')
            elif kind == 'Termination':
                self.usage = {k: value.get(k) for k in ('audio_duration_seconds', 'session_duration_seconds')}
                self.termination_confirmed = True
                self.terminated.set()
                return
            elif kind == 'Error' or 'error' in value:
                raise ValueError('Streaming provider unavailable')

    async def run(self):
        if self.attempted or self.closed:
            raise ValueError('Synthetic stream already consumed')
        self.attempted = True
        pcm = fixture_pcm(self.role)  # No browser/caller bytes, even through a forged client.
        self.deadline = time.monotonic() + 24
        try:
            async with asyncio.timeout(21):
                self.ws = await self.connector(URL, additional_headers={'Authorization': self.key.get_secret_value()},
                    open_timeout=5, close_timeout=.5, max_size=65536, proxy=None)
                self.reader = asyncio.create_task(self._receive())
                await asyncio.wait_for(self.begun.wait(), 3)
                start = self.audio_started_at = time.monotonic()
                for offset in range(0, len(pcm), 3200):
                    if self.closed:
                        raise ValueError('Synthetic stream withdrawn')
                    if self.reader.done():
                        await self.reader
                        raise ValueError('Streaming provider ended during audio')
                    await self.ws.send(pcm[offset:offset+3200])
                    await self.sleep(max(0, start + min(offset+3200, len(pcm))/32000 - time.monotonic()))
                self.audio_ended_at = time.monotonic()
                await self.ws.send(json.dumps({'type': 'ForceEndpoint'}))
                await self.sleep(1.5)
                if self.reader.done():
                    await self.reader
        finally:
            # Also runs on cancellation/errors; cleanup is shielded from caller cancellation.
            cleanup = asyncio.create_task(self._terminate())
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                await cleanup
                raise
        if self.closed or not self.termination_confirmed or not self.finals:
            raise ValueError('Synthetic transcription incomplete')
        return ' '.join(self.finals[i].strip() for i in sorted(self.finals))

    async def _terminate(self):
        if self.ws is None:
            return
        try:
            async with asyncio.timeout(max(.01, self.deadline - time.monotonic())):
                if not self.terminate_sent:
                    self.terminate_sent = True
                    await self.ws.send(json.dumps({'type': 'Terminate'}))
                if self.reader.done():
                    await self.reader
                await self.terminated.wait()
        finally:
            try:
                await asyncio.wait_for(self.ws.close(), .7)
            finally:
                if self.reader and not self.reader.done():
                    self.reader.cancel()
                    await asyncio.gather(self.reader, return_exceptions=True)

    async def close(self):
        # Owner cancels/awaits run(), which performs the bounded Terminate handshake.
        self.closed = True
