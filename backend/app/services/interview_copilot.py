"""One transient synthetic run; no runtime authorization, routes or persistence."""
from collections import OrderedDict
import hashlib
import json
from langsmith import tracing_context

from app.agents.copilot.workflow import Limits, build_graph
from app.schemas.interview_copilot import Binding, Result, Suggestion, Update


def fingerprint(suggestion):
    return hashlib.sha256((suggestion.criterion_id + ':' + suggestion.kind + ':' + suggestion.question).encode()).hexdigest()


def event_digest(event):
    # Generation is snapshot identity, not the identity of a recognized source event.
    return hashlib.sha256(json.dumps(event.model_dump(mode='json', exclude={'generation'}), sort_keys=True).encode()).hexdigest()


class CopilotLogic:
    """Serial owner of one replaceable update; not a concurrent live service.

    `submit` holds at most one snapshot; `process` consumes it synchronously.
    Live asynchronous delivery and authorization belong to 5B/5C, not this class.
    """
    def __init__(self, binding: Binding, *, limits: Limits | None = None):
        self.binding = Binding.model_validate(binding)
        self.limits = limits or Limits()
        self.graph = build_graph()
        self._pending = None
        self._generation = 0
        self._last_time = None
        self._last_emit = None
        self._history = OrderedDict()
        self._sources = OrderedDict()
        self._max_sequence = 0

    def clear(self):
        self._pending = None
        self._history.clear()
        self._sources.clear()
        self._last_emit = None
        # Keep generation/sequence fences: clear is not permission to replay.

    def submit(self, update: Update):
        update = Update.model_validate(update)
        if update.generation <= self._generation or (self._pending and update.generation <= self._pending.generation):
            return Result(status='rejected', reason='stale_generation', generation=update.generation)
        if update.binding != self.binding:
            self.clear()
            return Result(status='rejected', reason='invalid_context', generation=update.generation)
        self._pending = update
        return None

    def dismiss(self, suggestion: Suggestion, *, now_ms: int):
        if type(now_ms) is not int or now_ms < 0 or (self._last_time is not None and now_ms < self._last_time):
            return False
        key = fingerprint(suggestion)
        # Only an actually emitted suggestion can be dismissed.
        if key not in self._history:
            return False
        if now_ms - self._history[key] > self.limits.lifetime_ms:
            del self._history[key]
            return False
        self._last_time = now_ms
        self._history[key] = now_ms
        self._history.move_to_end(key)
        return True

    def process(self, *, now_ms: int):
        update, self._pending = self._pending, None
        if type(now_ms) is not int or now_ms < 0 or (self._last_time is not None and now_ms < self._last_time):
            self.clear()
            return Result(status='rejected', reason='invalid_context', generation=self._generation)
        if self._last_time is not None and now_ms - self._last_time > self.limits.lifetime_ms:
            self._history.clear(); self._sources.clear(); self._last_emit = None
        self._last_time = now_ms
        for key, when in list(self._history.items()):
            if now_ms - when > self.limits.lifetime_ms:
                del self._history[key]
        if update is None:
            return Result(status='abstained', reason='context_unavailable', generation=self._generation)
        self._generation = update.generation
        # Even an inherited LANGSMITH_TRACING setting must not export input text.
        with tracing_context(enabled=False):
            state = self.graph.invoke({'binding': self.binding, 'update': update, 'now_ms': now_ms, 'limits': self.limits},
                                      config={'callbacks': []})
        result = state['result']
        if result.status == 'rejected' or result.reason == 'context_expired':
            self.clear()
            return result
        for event in state.get('events', ()):
            old = self._sources.get(event.source)
            if (old is not None and old != event_digest(event)) or (old is None and event.source.sequence <= self._max_sequence):
                self.clear()
                return Result(status='rejected', reason='source_conflict', generation=update.generation)
        for event in state.get('events', ()):
            self._sources[event.source] = event_digest(event)
            self._max_sequence = max(self._max_sequence, event.source.sequence)
        while len(self._sources) > self.limits.history_size:
            self._sources.popitem(last=False)
        if result.status != 'suggested':
            return result
        suggestion = result.suggestions[0]
        if fingerprint(suggestion) in self._history:
            return result.model_copy(update={'status': 'abstained', 'reason': 'already_seen', 'suggestions': ()})
        if self._last_emit is not None and now_ms - self._last_emit < self.limits.cooldown_ms:
            return result.model_copy(update={'status': 'waiting', 'reason': 'cooldown', 'suggestions': ()})
        self._last_emit = now_ms
        self._history[fingerprint(suggestion)] = now_ms
        while len(self._history) > self.limits.history_size:
            self._history.popitem(last=False)
        return result
