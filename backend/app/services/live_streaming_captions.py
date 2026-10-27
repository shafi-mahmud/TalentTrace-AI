"""Per-authenticated-role live cloud captions, independent of assistant consent."""
import asyncio
from app.services.interview_captions import CaptionSession, ROLES

# Explicitly scoped development attempt budget; never an automatic retry mechanism.
ATTEMPTED = set()


class LiveStreamingCaptions(CaptionSession):
    def __init__(self, factory, interview, *, storage=None, clock=None):
        super().__init__(None, storage=storage, **({'clock':clock} if clock else {}))
        self.stream_factory, self.interview = factory, interview
        self.timeline = {role:[] for role in ROLES}
        self.publication_lock = asyncio.Lock()
        self.capture_timer = None
        self.failure = None

    def _provider_for(self, role):
        async def final(text, start_ms, end_ms):
            async with self.publication_lock:
                await self._check_access()
                if self.stopped or self.consent != ROLES:
                    return
                start = self._time(role, start_ms*16)
                end = self._time(role, min(end_ms*16,self.accepted_samples[role]), is_end=True)
                await self._publish_caption(role,text,start,end)
        return self.stream_factory(role,final,self._provider_failed)

    def active_event(self):
        return {**super().active_event(), 'source':'assemblyai-live'}

    def _provider_failed(self, category):
        if self.failure is None:
            self.failure = category
            asyncio.create_task(self._fail())

    async def _fail(self):
        try:
            await self.broadcast({'kind':'error','category':self.failure})
        finally:
            await self.stop()

    async def approve(self, role):
        if role not in self.peers or self.stopped:
            raise ValueError('Consent unavailable')
        if self.started is None and self.consent | {role} == ROLES:
            if self.interview in ATTEMPTED:
                await self.stop()
                raise ValueError('Live cloud attempt already consumed')
            ATTEMPTED.add(self.interview)
        await super().approve(role)
        if self.started is not None and not self.stopped and self.capture_timer is None:
            self.capture_timer = asyncio.create_task(self._capture_limit())

    async def _capture_limit(self):
        await asyncio.sleep(90)
        try:
            await self.request_finish('recruiter')
        except Exception:
            await self.stop()

    def _time(self, role, sample, *, is_end=False):
        for lower,upper,start in self.timeline[role]:
            if (lower <= sample < upper if not is_end else lower < sample <= upper or sample == lower == 0):
                return start+(sample-lower)/16000
        raise ValueError('Unverified recognition interval')

    async def audio(self, role, pcm):
        if (self.stopped or self.consent != ROLES or self.started is None or self.expired()
            or role not in self.peers or role in self.ends or role in self.tail_roles
            or role in self.processing
            or not isinstance(pcm,bytes) or not 0<len(pcm)<=3200 or len(pcm)%2
            or (len(pcm)!=3200 and not self.finishing)):
            raise ValueError('Live audio unavailable')
        now = self.clock()-self.started
        samples=len(pcm)//2
        lower=self.accepted_samples[role]
        if lower+samples>120*16000 or lower+samples>(now+.5)*16000 or len(self.timeline[role])>=1201:
            raise ValueError('Live audio limit')
        last = self.timeline[role][-1] if self.timeline[role] else None
        start=max(0,now-samples/16000,last[2]+(last[1]-last[0])/16000 if last else 0)
        if start+samples/16000>120:
            raise ValueError('Live audio interval limit')
        self.timeline[role].append((lower,lower+samples,start))
        self.frames[role]+=1; self.accepted_samples[role]+=samples
        if len(pcm)!=3200:self.tail_roles.add(role)
        self.processing.add(role); self.idle[role].clear()
        try:
            await self.providers[role].send(pcm)
        finally:
            self.processing.discard(role); self.idle[role].set()

    async def end_audio(self, role, value):
        await asyncio.wait_for(self.idle[role].wait(),2)
        await super().end_audio(role,value)

    async def _finalize(self):
        try:
            async with asyncio.timeout(35):
                await self.ended.wait()
                await self._check_access()
                await asyncio.gather(*(p.finish() for p in self.providers.values()))
                await self._check_access()
                if self.stopped or self.failure:
                    raise ValueError('Late provider result')
                # Use the provider's acknowledged audio duration, never turn a
                # successful socket send into invented recognition coverage.
                self.processed_samples = {role:min(self.accepted_samples[role],
                    int(provider.usage['audio_duration_seconds']*16000))
                    for role,provider in self.providers.items()}
                self.final_result=self.summary('drained' if self.processed_samples==self.accepted_samples else 'partial')
                await self.broadcast(self.final_result)
        except asyncio.CancelledError:
            raise
        except Exception:
            self.failure = self.failure or 'finalization_incomplete'
        finally:
            await self.stop()

    async def _cleanup(self):
        if self.capture_timer and self.capture_timer is not asyncio.current_task():
            self.capture_timer.cancel()
        await asyncio.gather(*(p.close() for p in self.providers.values()),return_exceptions=True)
        await asyncio.gather(*(asyncio.wait_for(send({'kind':'provider-termination',
            'confirmed':bool(self.providers) and all(p.termination_confirmed for p in self.providers.values()),
            'sessions':len(self.providers)}),1) for send in self.peers.values()),return_exceptions=True)
        await super()._cleanup()
        for values in self.timeline.values():values.clear()
