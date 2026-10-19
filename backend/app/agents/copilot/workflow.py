"""Model-free live assistance: bounded dialogue patterns, not competence analysis."""
from dataclasses import dataclass
import re
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from app.schemas.interview_copilot import Binding, Event, Exploration, Result, Suggestion, Update


@dataclass(frozen=True)
class Limits:
    max_events: int = 15
    max_characters: int = 12000
    lifetime_ms: int = 120000
    settle_ms: int = 3000
    cooldown_ms: int = 15000
    history_size: int = 64

    def __post_init__(self):
        if any(type(value) is not int for value in vars(self).values()) or not (1 <= self.max_events <= 15 and 1 <= self.max_characters <= 12000
                and 1 <= self.lifetime_ms <= 120000 and 0 <= self.settle_ms <= self.lifetime_ms
                and 0 <= self.cooldown_ms <= self.lifetime_ms and 1 <= self.history_size <= 64):
            raise ValueError('Invalid internal co-pilot limits.')


@dataclass(frozen=True, repr=False)
class Dialogue:
    question: tuple[Event, ...] = ()
    answer: tuple[Event, ...] = ()
    uncertain: bool = False


class State(TypedDict, total=False):
    binding: Binding
    update: Update
    now_ms: int
    limits: Limits
    events: tuple[Event, ...]
    dialogue: Dialogue
    exploration: tuple[Exploration, ...]
    choice: Suggestion | None
    result: Result
    waiting: bool


IGNORED = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'with', 'to', 'for',
           'skill', 'skills', 'experience', 'knowledge', 'required', 'preferred'}
NOISE = re.compile(r'^(?:[.?!\s]*|\[?(?:inaudible|silence|noise)\]?)$', re.I)
QUESTION = re.compile(r'^(?:explain|describe|what|why|how|tell me|can you|could you|do you|is|are)\b', re.I)
EXAMPLE = re.compile(r'\b(?:for example|for instance|here is an example|e\.g\.)', re.I)
UNFINISHED = re.compile(r'\b(?:and|or|because|the|a|to|with|if|so|is|are|can)\s*[,.]?$', re.I)


def tokens(text):
    return set(re.findall(r'[a-z0-9+#]+', text.casefold())) - IGNORED


def text(events):
    return ' '.join(e.text for e in events)


def associated(binding, question):
    observed = tokens(text(question))
    return [r for r in binding.requirements if tokens(r.description) and tokens(r.description) <= observed]


def references(events):
    return tuple(dict.fromkeys(e.source for e in events))


def render(kind, description):
    return {
        'explore': f'Could we explore this confirmed requirement next: {description}?',
        'example': f'Could you walk through a concrete example related to this requirement: {description}?',
        'clarify': f'Could we clarify or restate the recent question and response about this requirement: {description}?',
    }[kind]


def outcome(state, status, reason):
    return Result(status=status, reason=reason, generation=state['update'].generation,
                  exploration=state.get('exploration', ()))


def validate_context(state):
    update, limits, now = state['update'], state['limits'], state['now_ms']
    if update.binding != state['binding'] or len(update.events) > limits.max_events or sum(len(e.text) for e in update.events) > limits.max_characters:
        return {'result': outcome(state, 'rejected', 'invalid_context')}
    binding = update.binding
    found = {}
    for event in update.events:
        if (event.interview_id != binding.interview_id or event.run_id != binding.run_id
                or event.criteria_revision != binding.criteria_revision or event.generation != update.generation
                or event.source.caption_run_id != binding.caption_run_id or event.timestamp_ms > now):
            return {'result': outcome(state, 'rejected', 'invalid_context')}
        if event.source in found and found[event.source] != event:
            return {'result': outcome(state, 'rejected', 'source_conflict')}
        found[event.source] = event
    events = tuple(sorted(found.values(), key=lambda e: (e.timestamp_ms, e.source.sequence)))
    if events and now - events[0].timestamp_ms > limits.lifetime_ms:
        # Refuse rather than silently reinterpret a partial expired conversation.
        return {'result': outcome(state, 'abstained', 'context_expired')}
    return {'events': events}


def assemble_dialogue(state):
    question, answer, uncertain = [], [], False
    for event in state['events']:
        if not event.text or NOISE.fullmatch(event.text):
            if question:
                uncertain = True
            continue
        if event.role == 'recruiter':
            if QUESTION.match(event.text) or '?' in event.text:
                question, answer = [event], []
                uncertain = event.text.count('?') > 1
            elif question and not answer:
                question.append(event)
            elif question:
                uncertain = True
        elif question:
            answer.append(event)
            if '?' in event.text or QUESTION.match(event.text):
                uncertain = True
        # Candidate-first text is never relabelled as an interviewer question.
    dialogue = Dialogue(tuple(question), tuple(answer), uncertain)
    if not question:
        return {'dialogue': dialogue, 'result': outcome(state, 'abstained', 'insufficient_context')}
    if not answer or state['now_ms'] - state['events'][-1].timestamp_ms < state['limits'].settle_ms:
        return {'dialogue': dialogue, 'waiting': True}
    return {'dialogue': dialogue}


def track_exploration(state):
    binding, events, dialogue = state['binding'], state['events'], state['dialogue']
    states = {r.id: ('not_observed', ()) for r in binding.requirements}
    # Track earlier questions too, without treating candidate-only mentions as proof.
    question, answers = [], []
    def record():
        matches = associated(binding, question)
        for requirement in matches:
            uncertain = len(matches) != 1 or any('?' in e.text for e in answers)
            status = 'uncertain_association' if uncertain else 'response_observed' if answers else 'question_observed'
            states[requirement.id] = (status, references(tuple(question + answers)))
    for event in events:
        if event.role == 'recruiter' and (QUESTION.match(event.text) or '?' in event.text):
            record(); question, answers = [event], []
        elif event.role == 'recruiter' and question and not answers:
            question.append(event)
        elif event.role == 'candidate' and question and event.text and not NOISE.fullmatch(event.text):
            answers.append(event)
    record()
    matches = associated(binding, dialogue.question)
    if dialogue.uncertain:
        for r in matches:
            states[r.id] = ('uncertain_association', references(dialogue.question + dialogue.answer))
    exploration = tuple(Exploration(criterion_id=r.id, state=states[r.id][0], sources=states[r.id][1]) for r in binding.requirements)
    if state.get('waiting'):
        return {'exploration': exploration, 'result': Result(status='waiting', reason='fragments_pending',
                generation=state['update'].generation, exploration=exploration)}
    return {'exploration': exploration}


def choose(state):
    dialogue, binding = state['dialogue'], state['binding']
    matches = associated(binding, dialogue.question)
    if len(matches) != 1:
        return None
    requirement = matches[0]
    if dialogue.uncertain or UNFINISHED.search(text(dialogue.answer)):
        kind = 'clarify'
    elif not EXAMPLE.search(text(dialogue.answer)):
        # An invitation, never a claim that the candidate failed to give an example.
        kind = 'example'
    else:
        # Example-marker presence suppresses the example prompt, not proof of quality.
        requirement = next((r for r in binding.requirements if next(
            x.state for x in state['exploration'] if x.criterion_id == r.id) == 'not_observed'), None)
        if requirement is None:
            return None
        kind = 'explore'
    return Suggestion(criterion_id=requirement.id, kind=kind, question=render(kind, requirement.description),
                      sources=references(dialogue.question + dialogue.answer))


def select_follow_up(state):
    choice = choose(state)
    if choice is None:
        return {'result': outcome(state, 'abstained', 'ambiguous_association' if len(
            associated(state['binding'], state['dialogue'].question)) != 1 else 'insufficient_context')}
    return {'choice': choice}


def validate_output(state):
    choice = state.get('choice')
    # Re-derive the allowed contextual candidate, not just a valid-looking schema.
    expected = choose(state)
    if choice is None or expected is None or choice != expected:
        return {'result': outcome(state, 'rejected', 'unsupported_output')}
    valid_sources = {e.source for e in state['events']}
    if not set(choice.sources) <= valid_sources:
        return {'result': outcome(state, 'rejected', 'unsupported_output')}
    return {'result': Result(status='suggested', reason='valid_suggestion', generation=state['update'].generation,
                             exploration=state['exploration'], suggestions=(choice,))}


def build_graph():
    graph = StateGraph(State)
    for name, function in [('validate_context', validate_context), ('assemble_dialogue', assemble_dialogue),
                           ('track_exploration', track_exploration), ('select_follow_up', select_follow_up),
                           ('validate_output', validate_output)]:
        graph.add_node(name, function)
    graph.add_edge(START, 'validate_context')
    for name, following in [('validate_context', 'assemble_dialogue'), ('assemble_dialogue', 'track_exploration'),
                             ('select_follow_up', 'validate_output')]:
        graph.add_conditional_edges(name, lambda state: 'stop' if 'result' in state else 'next',
                                    {'stop': END, 'next': following})
    graph.add_conditional_edges('track_exploration', lambda state: 'stop' if 'result' in state else 'next',
                                {'stop': END, 'next': 'select_follow_up'})
    graph.add_edge('validate_output', END)
    return graph.compile(checkpointer=False)
