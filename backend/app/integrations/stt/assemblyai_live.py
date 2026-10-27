"""Development-only V3 PCM stream. No SDK retries, recordings or raw diagnostics."""
import asyncio
import hashlib
import json
import logging
import math
import time

from app.integrations.stt.assemblyai_synthetic import connect, URL

_QUIET_LOGGER = logging.Logger('talenttrace.assemblyai_live')
_QUIET_LOGGER.disabled = True
_QUIET_LOGGER.propagate = False  # SDK debug frames/headers must never enter application logs.


class AssemblyAILiveStream:
    def __init__(self, key, on_final, on_failure, *, connector=connect, lifetime=110, acknowledgement_timeout=5):
        if not 0 < lifetime <= 110 or not 0 < acknowledgement_timeout <= 5:
            raise ValueError('Bounded streaming lifetime required')
        self.key, self.on_final, self.on_failure = key, on_final, on_failure
        self.connector, self.lifetime, self.ack_timeout = connector, lifetime, acknowledgement_timeout
        self.ws = self.reader = self.watchdog = self.cleanup = None
        self.begun, self.terminated = asyncio.Event(), asyncio.Event()
        self.attempted = self.fenced = self.terminate_sent = self.termination_confirmed = False
        self.finals, self.pending_turns = {}, set()
        self.pending_audio = bytearray()
        self.accepted_samples = self.sent_samples = 0
        self.failure = None
        self.usage = None
        self.deadline = None

    def fail(self, category='provider_error'):
        if self.failure is None:
            self.failure = category
            self.on_failure(category)  # Owner schedules cleanup; never await the reader from itself.

    async def start(self):
        if self.attempted:
            raise ValueError('Stream already attempted')
        self.attempted = True
        self.deadline = time.monotonic() + self.lifetime + 7
        self.watchdog = asyncio.create_task(self._expire())
        try:
            self.ws = await asyncio.wait_for(self.connector(URL, additional_headers={'Authorization': self.key.get_secret_value()},
                open_timeout=5, close_timeout=.5, max_size=65536, max_queue=4, write_limit=65536,
                proxy=None, logger=_QUIET_LOGGER),5)
            self.reader = asyncio.create_task(self._receive())
            await asyncio.wait_for(self.begun.wait(), 5)
            if self.failure or self.fenced:
                raise ValueError('Streaming unavailable')
        except BaseException:
            await self.close()
            raise

    async def _expire(self):
        await asyncio.sleep(self.lifetime)
        self.fail('timeout')
        await self.close()

    async def send(self, pcm):
        if self.fenced or self.failure or not self.begun.is_set() or self.terminate_sent:
            raise ValueError('Stream unavailable')
        if not isinstance(pcm, bytes) or not 0 < len(pcm) <= 3200 or len(pcm) % 2:
            raise ValueError('Invalid PCM frame')
        if self.accepted_samples + len(pcm)//2 > 120*16000:
            raise ValueError('Audio limit')
        self.accepted_samples += len(pcm)//2
        self.pending_audio.extend(pcm)
        if len(self.pending_audio) >= 1600:
            frame = bytes(self.pending_audio)
            self.pending_audio.clear()
            self.sent_samples += len(frame)//2
            await asyncio.wait_for(self.ws.send(frame), 1)

    async def _receive(self):
        try:
            async for raw in self.ws:
                if not isinstance(raw, str) or len(raw) > 65536:
                    raise ValueError()
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError()
                kind = value.get('type')
                if kind == 'Begin':
                    if self.begun.is_set() or value.get('configuration', {}).get('model') != 'universal-streaming-english':
                        raise ValueError()
                    self.begun.set()
                elif kind == 'Turn':
                    if not self.begun.is_set():
                        raise ValueError()
                    await self._turn(value)
                elif kind == 'Termination':
                    if not self.terminate_sent:
                        raise ValueError()
                    keys = ('audio_duration_seconds', 'session_duration_seconds')
                    if any(type(value.get(k)) not in (int, float) or not math.isfinite(value[k]) or value[k] < 0 for k in keys):
                        raise ValueError()
                    self.usage = {k: value[k] for k in keys}
                    self.termination_confirmed = True
                    self.terminated.set()
                    return
                elif kind == 'Error' or 'error' in value:
                    raise ValueError()
                elif kind not in {'SpeechStarted', 'Heartbeat'}:
                    raise ValueError()
            if not self.termination_confirmed:
                raise ValueError()
        except asyncio.CancelledError:
            raise
        except Exception:
            self.fail()
            self.begun.set()  # Wake a failed startup, without treating it as success.

    async def _turn(self, value):
        order = value.get('turn_order')
        if type(order) is not int or not 0 <= order < 60:
            raise ValueError()
        if self.fenced:
            return
        if value.get('end_of_turn') is not True or value.get('turn_is_formatted') is not True:
            if order not in self.finals and value.get('transcript'):
                self.pending_turns.add(order)
            return
        text, words = value.get('transcript'), value.get('words')
        if self.terminate_sent and text == '' and words == []:
            # Documented Universal Streaming closing marker. Never fabricate text;
            # an earlier unresolved nonempty partial still makes finish incomplete.
            return
        if not isinstance(text, str) or not 0 < len(text.strip()) <= 1000 or any(ord(c)<32 or 127<=ord(c)<=159 for c in text):
            raise ValueError()
        if not isinstance(words, list) or not 0 < len(words) <= 300:
            raise ValueError()
        previous = 0
        for word in words:
            if (not isinstance(word, dict) or word.get('word_is_final') is not True
                or type(word.get('start')) is not int or type(word.get('end')) is not int
                or not previous <= word['start'] <= word['end'] <= math.ceil(self.accepted_samples/16)):
                raise ValueError()
            previous = word['end']
        start, end = words[0]['start'], words[-1]['end']
        signature = hashlib.sha256(json.dumps([text,start,end]).encode()).digest()
        if order in self.finals:
            if self.finals[order] != signature:
                raise ValueError('Conflicting final')
            return
        if self.finals and order <= max(self.finals):
            raise ValueError('Reordered final')
        self.finals[order] = signature
        self.pending_turns.discard(order)
        await self.on_final(text, start, end)

    async def finish(self):
        if self.fenced or self.failure:
            raise ValueError('Stream failed')
        if self.pending_audio:
            # Protocol minimum tail: explicit silence padding, not captured speech.
            tail = bytes(self.pending_audio); self.pending_audio.clear()
            tail += bytes(max(0,1600-len(tail)))
            self.sent_samples += len(tail)//2
            await asyncio.wait_for(self.ws.send(tail), 1)
        await self._end()
        if self.failure or not self.termination_confirmed or self.pending_turns:
            raise ValueError('Streaming finalization incomplete')

    async def _end(self):
        if self.cleanup is None:
            self.cleanup = asyncio.create_task(self._terminate())
        await asyncio.shield(self.cleanup)

    async def close(self):
        self.fenced = True  # Withdrawal rejects late text before any network await.
        self.pending_audio.clear()
        await self._end()

    async def _terminate(self):
        try:
            if self.ws is not None:
                async with asyncio.timeout(min(self.ack_timeout,max(.01,self.deadline-time.monotonic()))):
                    if not self.terminate_sent:
                        self.terminate_sent = True
                        await self.ws.send(json.dumps({'type':'Terminate'}))
                    await self.terminated.wait()
        except Exception:
            self.failure = self.failure or 'termination_unconfirmed'
        finally:
            if self.ws is not None:
                try:
                    await asyncio.wait_for(self.ws.close(), 1)
                except Exception:
                    self.failure = self.failure or 'termination_unconfirmed'
            if self.reader and not self.reader.done():
                self.reader.cancel()
                await asyncio.gather(self.reader, return_exceptions=True)
            if self.watchdog and self.watchdog is not asyncio.current_task():
                self.watchdog.cancel()
