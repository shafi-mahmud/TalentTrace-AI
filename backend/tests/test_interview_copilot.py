"""Synthetic, offline co-pilot contracts and graph/lifecycle regressions."""
from uuid import UUID, uuid4
import socket

import pytest
from pydantic import ValidationError

from app.agents.copilot import workflow
from app.agents.copilot.workflow import Limits
from app.schemas.interview_copilot import Binding, Event, Requirement, Source, Suggestion, Update
from app.services.interview_copilot import CopilotLogic


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('No external network permitted in co-pilot logic tests')
    monkeypatch.setattr(socket, 'create_connection', forbidden)
    monkeypatch.setattr(socket.socket, 'connect', forbidden)


@pytest.fixture
def binding():
    return Binding(interview_id=uuid4(), run_id=uuid4(), caption_run_id=uuid4(), criteria_revision=2,
                   requirements=(Requirement(id='python', description='Python'), Requirement(id='sql', description='SQL')))


def update(binding, rows=None, generation=1):
    rows = rows if rows is not None else [('recruiter', 'Explain Python.'), ('candidate', 'Python lists are mutable ordered sequences.')]
    events = tuple(Event(interview_id=binding.interview_id, run_id=binding.run_id,
        criteria_revision=binding.criteria_revision, generation=generation,
        source=Source(caption_run_id=binding.caption_run_id, sequence=i + 1), role=role,
        timestamp_ms=i * 1000, text=text) for i, (role, text) in enumerate(rows))
    return Update(synthetic=True, binding=binding, generation=generation, events=events)


def execute(binding, rows=None, *, now=6000, limits=None):
    logic = CopilotLogic(binding, limits=limits)
    logic.submit(update(binding, rows))
    return logic, logic.process(now_ms=now)


def test_definition_context_invites_example_without_claiming_it_was_missing(binding):
    _, result = execute(binding)
    assert result.status == 'suggested'
    suggestion = result.suggestions[0]
    assert suggestion.kind == 'example' and suggestion.criterion_id == 'python'
    assert [s.sequence for s in suggestion.sources] == [1, 2]
    assert suggestion.provisional is True
    assert 'failed' not in suggestion.question and 'lack' not in suggestion.question
    assert [x.state for x in result.exploration] == ['response_observed', 'not_observed']


def test_later_example_suppresses_example_and_explores_unobserved_requirement(binding):
    logic, first = execute(binding)
    rows = [('recruiter', 'Explain Python.'), ('candidate', 'Python lists are mutable ordered sequences.'),
            ('candidate', 'For example, append adds an item to a list.')]
    logic.submit(update(binding, rows, generation=2))
    result = logic.process(now_ms=22000)
    assert result.suggestions[0].kind == 'explore'
    assert result.suggestions[0].criterion_id == 'sql'
    assert result.suggestions[0].sources[-1].sequence == 3
    assert first.suggestions[0] != result.suggestions[0]


def test_no_generic_checklist_without_conversation(binding):
    assert execute(binding, [])[1].reason == 'insufficient_context'


def test_recruiter_question_without_response_waits(binding):
    result = execute(binding, [('recruiter', 'Explain Python.')])[1]
    assert result.status == 'waiting' and result.exploration[0].state == 'question_observed'


def test_fragment_settling_then_grouping(binding):
    rows = [('recruiter', 'Explain'), ('recruiter', 'Python.'),
            ('candidate', 'Python lists are'), ('candidate', 'Lists are mutable ordered sequences.')]
    assert execute(binding, rows, now=4000)[1].reason == 'fragments_pending'
    _, result = execute(binding, rows, now=7000)
    assert result.suggestions[0].kind == 'example'
    assert len(result.suggestions[0].sources) == 4


def test_settled_unfinished_response_waits(binding):
    _, result = execute(binding, [('recruiter', 'Explain Python.'), ('candidate', 'Python lists are mutable because')])
    assert not result.suggestions
    assert result.status in {'waiting', 'abstained'}


def test_candidate_question_is_uncertain_not_a_technical_answer(binding):
    _, result = execute(binding, [('recruiter', 'Explain Python.'), ('candidate', 'Do you mean lists or tuples?')])
    assert not result.suggestions
    assert result.status in {'waiting', 'abstained'}
    assert result.exploration[0].state == 'uncertain_association'


def test_out_of_order_and_exact_duplicate_events_are_normalized(binding):
    original = update(binding)
    shuffled = original.model_copy(update={'events': (original.events[1], original.events[0], original.events[1])})
    logic = CopilotLogic(binding)
    logic.submit(shuffled)
    result = logic.process(now_ms=6000)
    assert [s.sequence for s in result.suggestions[0].sources] == [1, 2]


def test_conflicting_duplicate_role_is_rejected(binding):
    original = update(binding)
    changed = original.events[0].model_copy(update={'role': 'candidate'})
    logic = CopilotLogic(binding)
    logic.submit(original.model_copy(update={'events': original.events + (changed,)}))
    assert logic.process(now_ms=6000).reason == 'source_conflict'


def test_candidate_first_is_never_relabelled_recruiter(binding):
    _, result = execute(binding, [('candidate', 'Explain Python.'), ('candidate', 'Python lists are mutable.')])
    assert result.status == 'abstained' and not result.suggestions


def test_two_requirement_question_abstains(binding):
    _, result = execute(binding, [('recruiter', 'Explain Python and SQL.'), ('candidate', 'I used both in a project.')])
    assert result.reason == 'ambiguous_association'
    assert all(e.state == 'uncertain_association' for e in result.exploration)


@pytest.mark.parametrize('noise', ['', '   ', '[inaudible]', '...', 'silence'])
def test_silence_and_noise_never_become_incompetence(binding, noise):
    result = execute(binding, [('candidate', noise)])[1]
    assert result.status == 'abstained' and result.suggestions == ()


@pytest.mark.parametrize('field', ['interview_id', 'run_id', 'caption_run_id', 'criteria_revision', 'requirements'])
def test_binding_mismatch_clears_pending_and_refuses_rebinding(binding, field):
    value = 3 if field == 'criteria_revision' else (Requirement(id='other', description='Other'),) if field == 'requirements' else uuid4()
    changed = binding.model_copy(update={field: value})
    logic = CopilotLogic(binding)
    logic.submit(update(binding))
    assert logic.submit(update(changed, generation=2)).reason == 'invalid_context'
    assert logic.process(now_ms=6000).reason == 'context_unavailable'


@pytest.mark.parametrize('field,value', [('interview_id', UUID(int=10)), ('run_id', UUID(int=11)),
                                       ('criteria_revision', 3), ('generation', 2)])
def test_event_identity_or_generation_mismatch(binding, field, value):
    original = update(binding)
    bad = original.events[0].model_copy(update={field: value})
    logic = CopilotLogic(binding)
    logic.submit(original.model_copy(update={'events': (bad, original.events[1])}))
    assert logic.process(now_ms=6000).reason == 'invalid_context'


def test_wrong_source_caption_run(binding):
    original = update(binding)
    bad = original.events[0].model_copy(update={'source': Source(caption_run_id=uuid4(), sequence=1)})
    logic = CopilotLogic(binding); logic.submit(original.model_copy(update={'events': (bad, original.events[1])}))
    assert logic.process(now_ms=6000).status == 'rejected'


def test_stale_generation_cannot_replace_newer_pending(binding):
    logic = CopilotLogic(binding)
    logic.submit(update(binding, generation=2))
    assert logic.submit(update(binding)).reason == 'stale_generation'
    assert logic.process(now_ms=6000).generation == 2
    assert logic.submit(update(binding, generation=2)).reason == 'stale_generation'


def test_single_replaceable_pending_snapshot(binding):
    logic = CopilotLogic(binding)
    logic.submit(update(binding))
    rows = [('recruiter', 'Explain SQL.'), ('candidate', 'SQL groups database operations.')]
    logic.submit(update(binding, rows, generation=2))
    assert logic.process(now_ms=6000).suggestions[0].criterion_id == 'sql'
    assert logic.process(now_ms=6001).reason == 'context_unavailable'


def test_cooldown_applies_to_changed_context(binding):
    logic, _ = execute(binding)
    rows = [('recruiter', 'Explain Python.'), ('candidate', 'Python lists are mutable ordered sequences.'),
            ('candidate', 'For example, append adds an item to a list.')]
    logic.submit(update(binding, rows, generation=2))
    assert logic.process(now_ms=7000).reason == 'cooldown'
    logic.submit(update(binding, rows, generation=3))
    assert logic.process(now_ms=21000).suggestions[0].kind == 'explore'


def test_dismissed_and_emitted_suggestions_do_not_repeat(binding):
    logic, result = execute(binding)
    assert logic.dismiss(result.suggestions[0], now_ms=6000)
    logic.submit(update(binding, generation=2))
    assert logic.process(now_ms=22000).reason == 'already_seen'
    assert len(logic._history) == 1


def test_expiration_removes_pending_text_and_history(binding):
    logic, _ = execute(binding)
    logic.submit(update(binding, generation=2))
    assert logic.process(now_ms=130001).reason == 'context_expired'
    assert logic._pending is None and not logic._history and not logic._sources


def test_size_limits_and_internal_configuration(binding):
    with pytest.raises(ValidationError):
        update(binding, [('candidate', 'a')] * 16)
    with pytest.raises(ValidationError):
        update(binding, [('candidate', 'a' * 1000)] * 13)
    assert execute(binding, limits=Limits(max_events=1))[1].reason == 'invalid_context'
    assert execute(binding, limits=Limits(max_characters=10))[1].reason == 'invalid_context'
    with pytest.raises(ValueError):
        Limits(max_events=16)


def test_source_role_cannot_change_across_generations(binding):
    logic, _ = execute(binding)
    revised = update(binding, generation=2)
    revised = revised.model_copy(update={'events': (revised.events[0].model_copy(update={'role': 'candidate'}), revised.events[1])})
    logic.submit(revised)
    assert logic.process(now_ms=22000).reason == 'source_conflict'


@pytest.mark.parametrize('bad', ['question', 'criterion_id', 'sources'])
def test_output_validation_rejects_unsupported_assumptions_or_references(binding, monkeypatch, bad):
    def malicious(state):
        value = workflow.choose(state)
        fields = {'question': 'The candidate failed Python. Reject them.'} if bad == 'question' else {'criterion_id': 'invented'} if bad == 'criterion_id' else {'sources': (Source(caption_run_id=uuid4(), sequence=999),)}
        return {'choice': value.model_copy(update=fields)}
    monkeypatch.setattr(workflow, 'select_follow_up', malicious)
    _, result = execute(binding)
    assert result.reason == 'unsupported_output' and not result.suggestions


def test_invalid_contract_cannot_hide_extra_data_or_controls(binding):
    with pytest.raises(ValidationError):
        Requirement(id='python', description='Python\nInjected content')
    with pytest.raises(ValidationError):
        Requirement(id='bad id', description='Python')
    with pytest.raises(ValidationError):
        Binding.model_validate(binding.model_copy(update={'criteria_revision': True}))
    with pytest.raises(ValidationError):
        Update.model_validate(update(binding).model_copy(update={'synthetic': False}))


def test_logic_has_no_provider_database_or_persistence_dependencies(binding, monkeypatch, caplog):
    import app.core.auth as auth
    import app.integrations.llm.interview_evaluation as provider
    def forbidden(*args, **kwargs):
        raise AssertionError('Forbidden external dependency')
    monkeypatch.setattr(auth, 'session_factory', forbidden)
    monkeypatch.setattr(provider.GroqInterviewAssessment, 'assess', forbidden)
    _, result = execute(binding)
    assert result.status == 'suggested'
    assert not caplog.records


def test_graph_has_real_stages_and_no_checkpointer(binding):
    logic = CopilotLogic(binding)
    assert set(logic.graph.get_graph().nodes) == {'__start__', '__end__', 'validate_context',
        'assemble_dialogue', 'track_exploration', 'select_follow_up', 'validate_output'}
    assert not logic.graph.checkpointer


def test_external_tracing_environment_cannot_enable_graph_export(binding, monkeypatch, caplog):
    monkeypatch.setenv('LANGSMITH_TRACING', 'true')
    monkeypatch.setenv('LANGCHAIN_TRACING_V2', 'true')
    monkeypatch.setenv('LANGSMITH_API_KEY', 'synthetic-not-a-real-key')
    assert execute(binding)[1].status == 'suggested'
    assert not caplog.records


def test_future_timestamp_clock_regression_and_invalid_dismiss_are_rejected(binding):
    logic = CopilotLogic(binding)
    logic.submit(update(binding))
    assert logic.process(now_ms=0).reason == 'invalid_context'
    other, result = execute(binding)
    assert not other.dismiss(result.suggestions[0], now_ms=-1)
    assert other.process(now_ms=1).status == 'rejected'


def test_dedup_and_source_history_are_bounded_and_evicted_sources_cannot_replay(binding):
    logic = CopilotLogic(binding, limits=Limits(history_size=2, cooldown_ms=0))
    for generation in range(1, 5):
        topic = 'Python' if generation % 2 else 'SQL'
        response = topic + (' is used in a project.' if generation <= 2 else ' is used for example in a project.')
        value = update(binding, [('recruiter', 'Explain ' + topic + '.'), ('candidate', response)], generation=generation)
        value = value.model_copy(update={'events': tuple(e.model_copy(update={
            'source': Source(caption_run_id=binding.caption_run_id, sequence=e.source.sequence + generation * 2)}) for e in value.events)})
        logic.submit(value)
        logic.process(now_ms=6000 + generation)
    assert len(logic._sources) == 2 and len(logic._history) == 2
    logic.submit(update(binding, generation=5))
    assert logic.process(now_ms=7000).reason == 'source_conflict'


def test_exact_context_lifetime_boundary_and_more_than_boundary(binding):
    assert execute(binding, now=120000)[1].status == 'suggested'
    assert execute(binding, now=120001)[1].reason == 'context_expired'


def test_input_cannot_override_internal_limits_or_duplicate_requirement_ids(binding):
    with pytest.raises(ValidationError):
        Update.model_validate({**update(binding).model_dump(), 'limits': {'cooldown_ms': 0}})
    with pytest.raises(ValidationError):
        Binding.model_validate(binding.model_copy(update={'requirements': (
            Requirement(id='python', description='Python'), Requirement(id='PYTHON', description='Python'))}))


def test_no_database_queries_or_text_files_created(binding, monkeypatch):
    from pathlib import Path
    from sqlalchemy.ext.asyncio import AsyncSession
    def forbidden(*args, **kwargs):
        raise AssertionError('Co-pilot logic cannot persist anything')
    monkeypatch.setattr(AsyncSession, 'execute', forbidden)
    monkeypatch.setattr(AsyncSession, 'commit', forbidden)
    monkeypatch.setattr(Path, 'write_text', forbidden)
    assert execute(binding)[1].status == 'suggested'


def test_expired_dismissal_cannot_renew_old_suggestion(binding):
    logic, result = execute(binding)
    assert not logic.dismiss(result.suggestions[0], now_ms=130001)
    assert not logic._history


@pytest.mark.parametrize('answer,status', [
    ('I travelled by bus this morning.', 'abstained'),
    ('[uncertain speech]', 'abstained'),
    ('Python lists are [inaudible].', 'abstained'),
    ('Python lists are ...', 'waiting'),
    ('Python lists are', 'waiting'),
    ('SQL queries return rows.', 'abstained'),
    ('Do you mean lists or tuples?', 'abstained'),
])
def test_quality_gate_unsafe_response(binding, answer, status):
    result = execute(binding, [('recruiter', 'Explain Python lists.'), ('candidate', answer)])[1]
    assert result.status == status
    assert not result.suggestions
    if status == 'abstained':
        assert result.exploration[0].state == 'uncertain_association'


def test_subtopic_without_requirement_repetition(binding):
    result = execute(binding, [('recruiter', 'Explain Python lists.'),
        ('candidate', 'Lists are mutable ordered sequences.')])[1]
    assert result.suggestions[0].kind == 'example'


def test_completed_fragment_preserves_sources(binding):
    rows = [('recruiter', 'Explain Python lists.'), ('candidate', 'Python lists are ...')]
    assert execute(binding, rows)[1].status == 'waiting'
    rows.append(('candidate', 'Lists are mutable ordered sequences.'))
    result = execute(binding, rows, now=8000)[1]
    assert result.suggestions[0].kind == 'example'
    assert [x.sequence for x in result.suggestions[0].sources] == [1, 2, 3]


def test_unrelated_completed_turn_cannot_be_concatenated(binding):
    result = execute(binding, [('recruiter', 'Explain Python lists.'),
        ('candidate', 'Python lists are mutable.'), ('candidate', 'I travelled by bus.')])[1]
    assert result.status == 'abstained' and not result.suggestions


def test_latest_unrelated_question_changes_outcome(binding):
    rows = [('recruiter', 'Explain Python lists.'), ('candidate', 'Lists are mutable.')]
    assert execute(binding, rows)[1].status == 'suggested'
    rows += [('recruiter', 'How was your journey?'), ('candidate', 'I travelled by bus.')]
    assert execute(binding, rows, now=9000)[1].status == 'abstained'


@pytest.mark.parametrize('answer', ['For example, I travelled by bus.',
    'Python and SQL were both mentioned.', 'Unintelligible speech', '[low confidence] lists are mutable'])
def test_independent_counterexamples(binding, answer):
    result = execute(binding, [('recruiter', 'Explain Python lists.'), ('candidate', answer)])[1]
    assert result.status == 'abstained' and not result.suggestions


def test_validator_does_not_call_selector(binding, monkeypatch):
    original = workflow.choose
    def select_then_disable(state):
        choice = original(state)
        monkeypatch.setattr(workflow, 'choose', lambda _: (_ for _ in ()).throw(AssertionError('selector repeated')))
        return {'choice': choice}
    monkeypatch.setattr(workflow, 'select_follow_up', select_then_disable)
    assert execute(binding)[1].status == 'suggested'


@pytest.mark.parametrize('answer', ['I travelled by bus.', '[uncertain speech]', 'SQL returns rows.'])
def test_validator_rejects_forged_selector_association(binding, monkeypatch, answer):
    def forged(state):
        return {'choice': Suggestion(criterion_id='python', kind='example',
            question=workflow.render('example', 'Python'),
            sources=workflow.references(state['dialogue'].question + state['dialogue'].answer))}
    monkeypatch.setattr(workflow, 'select_follow_up', forged)
    result = execute(binding, [('recruiter', 'Explain Python lists.'), ('candidate', answer)])[1]
    assert result.status == 'abstained' and not result.suggestions


@pytest.mark.parametrize('continuation', ['I travelled by bus.', 'SQL returns rows.', 'travelled by bus.', 'mutable ordered sequences.'])
def test_unfinished_fragment_does_not_justify_unrelated_continuation(binding, continuation):
    result = execute(binding, [('recruiter', 'Explain Python lists.'),
        ('candidate', 'Python lists are ...'), ('candidate', continuation)], now=8000)[1]
    assert result.status == 'abstained' and not result.suggestions


def test_independent_validator_rejects_stale_dialogue(binding):
    value = update(binding, [('recruiter', 'Explain Python lists.'), ('candidate', 'Lists are mutable.'),
        ('recruiter', 'How was your journey?'), ('candidate', 'I travelled by bus.')])
    state = {'binding': binding, 'update': value, 'events': value.events,
        'dialogue': workflow.Dialogue(value.events[:1], value.events[1:2]), 'exploration': (),
        'choice': Suggestion(criterion_id='python', kind='example', question=workflow.render('example', 'Python'),
            sources=workflow.references(value.events[:2]))}
    result = workflow.validate_output(state)['result']
    assert result.status == 'abstained' and result.reason == 'unsupported_output'


def test_validator_refuses_role_swapped_dialogue(binding):
    value = update(binding)
    question = value.events[0].model_copy(update={'role': 'candidate'})
    state = {'binding': binding, 'update': value, 'events': value.events,
        'dialogue': workflow.Dialogue((question,), value.events[1:]), 'exploration': (),
        'choice': Suggestion(criterion_id='python', kind='example', question=workflow.render('example', 'Python'),
            sources=workflow.references(value.events))}
    assert workflow.validate_output(state)['result'].status == 'abstained'



def test_different_subtopic_question_does_not_reuse_previous_association(binding):
    answer = ('candidate', 'Lists are mutable ordered sequences.')
    assert execute(binding, [('recruiter', 'Explain Python lists.'), answer])[1].status == 'suggested'
    result = execute(binding, [('recruiter', 'Explain Python decorators.'), answer])[1]
    assert result.status == 'abstained' and not result.suggestions
