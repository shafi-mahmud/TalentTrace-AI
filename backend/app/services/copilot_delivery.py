"""Bounded process-local delivery. No database writes or providers."""
from dataclasses import dataclass, field
import threading
import math
import time
from uuid import UUID, uuid4

from app.schemas.interview_copilot import Binding, Requirement, Update
from app.core.config import settings
from app.services.interview_copilot import CopilotLogic, fingerprint

VERSION = 'local-copilot-v1'
DISCLOSURE = ('The interview assistant can temporarily process recognized speech from this interview '
    'to suggest job-related follow-up questions to the interviewer. Suggestions are not shown to the candidate. '
    'This feature does not automatically score or decide hiring outcomes. This version processes speech locally '
    'without sending it to an external AI provider, and does not retain an additional saved co-pilot transcript.')

CLOUD_DISCLOSURE = (
    'AssemblyAI transcribes only the fixed server-owned synthetic eSpeak audio; free-tier audio and text '
    'may be used for model training. Physical microphone audio is not sent to AssemblyAI. '
    'The local interview assistant temporarily uses those captions for job-related interviewer-only '
    'follow-up questions. Both caption and assistant consents are required. No automatic scoring or '
    'hiring decisions; no additional saved co-pilot transcript.')


def disclosure():
    return CLOUD_DISCLOSURE if settings.assemblyai_synthetic_enabled else DISCLOSURE


class Unavailable(Exception):
    """Fixed diagnostic only; never source text or credentials."""


@dataclass(frozen=True, repr=False)
class Access:
    interview: UUID
    job: UUID
    revision: int
    owner: UUID
    recruiter_key: str
    candidate_key: str
    requirements: tuple[Requirement, ...]
    deadline: float
    blocked: bool = False


@dataclass(repr=False)
class Run:
    access: Access
    binding: Binding
    born: float
    expires: float
    epoch: int = 1
    consents: set = field(default_factory=set)
    revoked: bool = False
    active_after_ms: int | None = None
    logic: CopilotLogic | None = None
    result: object = None
    result_until: float = 0
    busy: bool = False
    live: bool = False


class Delivery:
    """One serialized publication fence per process, maximum 32 two-minute runs.

    Worker results publish only under their original run/epoch. Invalidating the
    run increments the fence before releasing any transient context. No executor,
    task queue, provider, checkpoint or persistence is created by this class.
    """
    def __init__(self, clock=time.time):
        self.clock = clock
        self.lock = threading.RLock()
        self.runs = {}
        self.listeners = {}

    def listen(self, interview, callback):
        with self.lock:
            self.listeners[interview] = callback

    def unlisten(self, interview, callback):
        with self.lock:
            if self.listeners.get(interview) == callback:
                self.listeners.pop(interview, None)

    def clear_run(self, run):
        run.epoch += 1
        run.revoked = True
        run.consents.clear()
        run.active_after_ms = None
        if run.logic:
            run.logic.clear()
        run.logic = None
        run.result = None
        run.busy = False
        callback = self.listeners.get(run.access.interview)
        if callback:
            try:
                callback()
            except Exception:
                pass  # Assistant cleanup never propagates to F4/privacy.

    def invalidate(self, interview):
        with self.lock:
            if interview in self.runs:
                self.clear_run(self.runs[interview])

    def clear(self):
        with self.lock:
            for run in self.runs.values():
                self.clear_run(run)
            self.runs.clear()
            self.listeners.clear()

    def sweep(self):
        with self.lock:
            now = self.clock()
            for key, run in list(self.runs.items()):
                if now >= run.expires or now >= run.access.deadline:
                    self.clear_run(run)
                    del self.runs[key]
                elif now >= run.result_until:
                    run.result = None

    def recruiter_key(self, interview):
        with self.lock:
            run = self.runs.get(interview)
            return run.access.recruiter_key if run else ''

    def checked(self, access):
        # Caller holds lock. Always compare the complete current DB-derived scope.
        self.sweep()
        run = self.runs.get(access.interview)
        if run and (access.blocked or run.access != access):
            self.clear_run(run)
        return run

    def prepare(self, access, *, caption_run_id=None):
        with self.lock:
            self.sweep()
            if access.blocked or self.clock() >= access.deadline:
                raise Unavailable('copilot_unavailable')
            if access.interview not in self.runs and len(self.runs) >= 32:
                raise Unavailable('copilot_capacity')
            self.invalidate(access.interview)
            binding = Binding(interview_id=access.interview, run_id=uuid4(), caption_run_id=caption_run_id or uuid4(),
                criteria_revision=access.revision, requirements=access.requirements)
            now = self.clock()
            self.runs[access.interview] = Run(access, binding, now, min(now + 120, access.deadline), live=caption_run_id is not None)
            return self.view(access)

    def identity(self, run, run_id, epoch):
        if not run or run.binding.run_id != run_id or run.epoch != epoch:
            raise Unavailable('copilot_run_changed')

    def decide(self, access, role, run_id, epoch, decision):
        with self.lock:
            run = self.checked(access)
            self.identity(run, run_id, epoch)
            if role not in {'recruiter', 'candidate'}:
                raise Unavailable('copilot_participant_unavailable')
            if run.revoked:
                raise Unavailable('copilot_withdrawn')
            if decision != 'accept':
                self.clear_run(run)
            else:
                run.consents.add(role)
                if len(run.consents) == 2 and run.logic is None:
                    run.active_after_ms = math.ceil((self.clock() - run.born) * 1000)
                    run.logic = CopilotLogic(run.binding)
            return self.view(access)

    def view(self, access, *, recruiter=False):
        with self.lock:
            run = self.checked(access)
            status = 'unavailable' if run is None else 'withdrawn' if run.revoked else (
                'authorized' if len(run.consents) == 2 else 'awaiting_consent')
            value = dict(enabled=True, live_connected=bool(run and run.live and not run.revoked), version=VERSION, wording=disclosure(),
                status=status, run_id=str(run.binding.run_id) if run else None,
                epoch=run.epoch if run else 0, recruiter_consented=bool(run and 'recruiter' in run.consents),
                candidate_consented=bool(run and 'candidate' in run.consents),
                expires_in_ms=max(0, int((run.expires-self.clock())*1000)) if run else 0)
            if recruiter:
                value['suggestion'] = None
                value['processing'] = 'not_connected'
                if run and status == 'authorized' and run.result:
                    value['processing'] = run.result.status
                    if run.result.suggestions:
                        suggestion = run.result.suggestions[0]
                        requirement = next(r for r in run.binding.requirements if r.id == suggestion.criterion_id)
                        value['suggestion'] = dict(id=fingerprint(suggestion), question=suggestion.question,
                            requirement=requirement.description, provisional=True,
                            reason=('Recognized caption source events ' if run.live else 'Internal synthetic source events ')+', '.join(str(s.sequence) for s in suggestion.sources)
                            +'; lexical association only, not a competence assessment.')
            return value

    def dismiss(self, access, run_id, epoch, suggestion_id):
        with self.lock:
            run = self.checked(access)
            self.identity(run, run_id, epoch)
            if run.revoked or not run.logic or not run.result or not run.result.suggestions:
                raise Unavailable('copilot_suggestion_unavailable')
            suggestion = run.result.suggestions[0]
            if fingerprint(suggestion) != suggestion_id:
                raise Unavailable('copilot_suggestion_changed')
            run.logic.dismiss(suggestion, now_ms=int((self.clock()-run.born)*1000))
            run.result = None
            return self.view(access, recruiter=True)

    def live_context(self, interview, caption_run_id):
        with self.lock:
            self.sweep()
            run = self.runs.get(interview)
            if (not run or not run.live or run.revoked or len(run.consents) != 2
                    or run.binding.caption_run_id != caption_run_id):
                return None
            return run.binding, run.epoch, run.born, run.born + run.active_after_ms / 1000

    def hide_result(self, interview):
        with self.lock:
            run = self.runs.get(interview)
            if run:
                run.result = None

    def publish_live(self, access, run_id, epoch, result, guard):
        with self.lock:
            run = self.checked(access)
            self.identity(run, run_id, epoch)
            if run.revoked or len(run.consents) != 2 or not guard():
                raise Unavailable('copilot_context_changed')
            run.result = result
            run.result_until = min(run.expires, self.clock()+15)

    def submit_live(self, access, update, guard):
        return self._submit(access, update, live=True, guard=guard)

    def submit_synthetic(self, access, update: Update):
        return self._submit(access, update)

    def _submit(self, access, update: Update, *, live=False, guard=lambda: True):
        """Internal bounded processor. Public routes never submit transcript events.

        Use original run-relative timestamps strictly after two-party consent;
        never remap pre-consent events to make them eligible.
        """
        update = Update.model_validate(update)
        with self.lock:
            run = self.checked(access)
            if (not run or run.revoked or len(run.consents) != 2 or not run.logic or run.busy
                    or run.live != live or not guard()
                    or update.binding != run.binding or not update.events
                    or any(e.timestamp_ms <= run.active_after_ms for e in update.events)):
                raise Unavailable('copilot_context_unavailable')
            run.busy = True
            epoch, logic = run.epoch, run.logic
            now_ms = int((self.clock()-run.born)*1000)
        try:
            rejected = logic.submit(update)
            result = rejected or logic.process(now_ms=now_ms)
        except Exception:
            # No source/exception content leaks. Failure does not affect F4.
            with self.lock:
                if self.runs.get(access.interview) is run and run.epoch == epoch:
                    self.clear_run(run)
            raise Unavailable('copilot_processing_unavailable') from None
        with self.lock:
            current = self.checked(access)
            if current is not run or run.epoch != epoch or run.revoked or not guard():
                if current is run:
                    run.busy = False
                raise Unavailable('copilot_context_changed')
            run.busy = False
            if live:
                return result
            run.result = result
            run.result_until = min(run.expires, self.clock()+15)
            return self.view(access, recruiter=True)


delivery = Delivery()
