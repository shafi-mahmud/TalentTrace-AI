"""Internal F4 recognition adapter. No HTTP ingestion, audio retention or provider."""
import asyncio
import math
import threading
from app.schemas.interview_copilot import Event, Source, Update
from app.services.copilot_delivery import Unavailable

# At most one offloaded graph calculation across caption-run replacements.
PROCESSOR = threading.BoundedSemaphore(1)


class LiveBridge:
    def __init__(self, interview, caption_run_id, manager, authorize, *, settle=3.05):
        self.interview, self.caption_run_id = interview, caption_run_id
        self.manager, self.authorize = manager, authorize
        self.settle = settle
        self.loop = asyncio.get_running_loop()
        self.lock = threading.RLock()
        self.records = []
        self.last_sequence, self.last_end = 0, -1
        self.generation = 0
        self.context = None
        self.task = None
        self.closed = False
        manager.invalidate(interview)  # A replacement caption run cannot reuse consent.
        manager.listen(interview, self.clear)

    def clear(self):
        with self.lock:
            self.generation += 1
            self.records.clear()
            self.context = None
            task = self.task
            self.task = None
        # Callbacks may be invoked from the bounded graph thread.
        if task and task is not asyncio.current_task(self.loop):
            self.loop.call_soon_threadsafe(task.cancel)

    def close(self):
        self.closed = True
        self.clear()
        self.manager.invalidate(self.interview)
        self.manager.unlisten(self.interview, self.clear)

    def offer(self, caption_run_id, origin_wall, event):
        """Called synchronously ONLY by CaptionSession after safe STT recognition.

        Audio interval uses the real caption start clock, so slow recognition of
        pre-consent buffered audio cannot become post-consent evidence.
        """
        if self.closed or caption_run_id != self.caption_run_id or origin_wall is None:
            return
        if (set(event) != {'kind','role','sequence','start','end','text'} or event['kind'] != 'caption'
                or event['role'] not in {'recruiter','candidate'} or type(event['sequence']) is not int
                or event['sequence'] <= self.last_sequence):
            return
        start, end = event['start'], event['end']
        if (type(start) not in {int,float} or type(end) not in {int,float}
                or not math.isfinite(start) or not math.isfinite(end) or not 0 <= start <= end <= 300
                or end < self.last_end):
            return
        self.last_sequence, self.last_end = event['sequence'], end
        current = self.manager.live_context(self.interview, self.caption_run_id)
        if current is None:
            self.clear()
            return
        binding, epoch, born, cutoff = current
        # Strict whole-chunk cutoff; recognition return time is irrelevant.
        if origin_wall + start <= cutoff:
            return
        identity = binding.run_id, epoch
        if self.context != identity:
            self.clear()
            self.context = identity
        try:
            record = Event(interview_id=self.interview, run_id=binding.run_id,
                criteria_revision=binding.criteria_revision, generation=1,
                source=Source(caption_run_id=caption_run_id,sequence=event['sequence']),role=event['role'],
                timestamp_ms=int((origin_wall+end-born)*1000), audio_start_ms=int(start*1000),
                audio_end_ms=int(end*1000), text=event['text'])
        except (ValueError, TypeError):
            return
        if len(self.records) >= 15 or sum(len(e.text) for e in self.records)+len(record.text) > 12000:
            self.close()  # Do not silently turn an overflow into a partial conversation.
            return
        self.records.append(record)
        self.generation += 1
        self.manager.hide_result(self.interview)  # New speech supersedes the previous question.
        if self.task is None or self.task.done():
            self.task = self.loop.create_task(self._work())

    async def _work(self):
        try:
            while not self.closed and self.records:
                generation = self.generation
                await asyncio.sleep(self.settle)
                if generation != self.generation:
                    continue
                current = self.manager.live_context(self.interview, self.caption_run_id)
                if current is None:
                    self.clear()
                    return
                binding, epoch, _, _ = current
                update = Update(synthetic=True,binding=binding,generation=generation,
                    events=tuple(e.model_copy(update={'generation':generation}) for e in self.records))
                # Both websocket participants and full F11 ownership/scope are rechecked.
                access = await asyncio.wait_for(self.authorize(),2)
                if access.interview != self.interview:
                    raise Unavailable('copilot_interview_changed')
                guard = lambda: not self.closed and generation == self.generation and self.context == (binding.run_id,epoch)
                if not PROCESSOR.acquire(blocking=False):
                    await asyncio.sleep(0.2)
                    continue
                def calculate():
                    try:
                        return self.manager.submit_live(access,update,guard)
                    finally:
                        PROCESSOR.release()
                try:
                    future = self.loop.run_in_executor(None, calculate)
                    # Cancellation must not cancel a queued calculation before its
                    # finally releases the single global processing slot.
                    future.add_done_callback(lambda f: None if f.cancelled() else f.exception())
                    result = await asyncio.shield(future)
                except Unavailable:
                    if not guard():
                        continue
                    raise
                # Fresh DB authorization after slow calculation, before publication.
                access = await asyncio.wait_for(self.authorize(),2)
                self.manager.publish_live(access,binding.run_id,epoch,result,guard)
                if generation == self.generation:
                    return
        except asyncio.CancelledError:
            return
        except Exception:
            # Fixed fail-closed state only; never log speech, SQL or credentials.
            self.close()
        finally:
            if self.task is asyncio.current_task():
                self.task = None
