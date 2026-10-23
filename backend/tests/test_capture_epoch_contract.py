"""Bounded epoch contracts with synthetic source records and controllable clocks."""
import asyncio
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from app.services.evaluation_input import build_input, EvaluationInputError
from app.services.interview_qa import pair_transcript
from app.services.interview_captions import CaptionSession
from test_evaluation_input import source
from test_caption_finalization import ready


def two():
    parent, snapshot, captures, turns = source()
    second = deepcopy(captures[0])
    second.id = uuid4()
    second.started_at += timedelta(seconds=15)
    second.ended_at += timedelta(seconds=15)
    second.recruiter_consented_at = second.candidate_consented_at = second.started_at
    more = deepcopy(turns)
    for row in more:
        row.id = uuid4()
        row.session_id = second.id
    return parent, snapshot, captures + [second], turns + more


def test_gap_is_derived_from_persisted_windows_and_never_cross_pairs():
    data = build_input(*two())
    assert len(data.captures) == 2 and len(data.turns) == 4
    assert '5000 ms between stored capture windows' in data.warning
    assert 'Transition audio coverage is unverified' in data.warning
    assert data.scope == 'accepted_audio_only'
    pairs = pair_transcript(data)
    by_id = {t.id: t for t in data.turns}
    assert len(pairs) == 2
    for pair in pairs:
        assert all(by_id[t].session_id == pair.capture_id for t in pair.question_turns + pair.answer_turns)


@pytest.mark.parametrize('defect', ['overlap', 'partial_first', 'foreign_epoch', 'duplicate_event'])
def test_invalid_epoch_history_cannot_be_complete_evidence(defect):
    parent, snapshot, captures, turns = two()
    if defect == 'overlap':
        captures[1].started_at = captures[0].ended_at - timedelta(microseconds=1)
        captures[1].recruiter_consented_at = captures[1].candidate_consented_at = captures[1].started_at
    if defect == 'partial_first': captures[0].status = 'interrupted'; captures[0].persistence_outcome = 'partial'
    if defect == 'foreign_epoch': turns[-1].session_id = uuid4()
    if defect == 'duplicate_event': turns[-1].id = turns[0].id
    with pytest.raises(EvaluationInputError): build_input(parent, snapshot, captures, turns)


def test_second_epoch_does_not_renew_absolute_authorization_deadline():
    clock = [0.0]
    first = CaptionSession(lambda: None, clock=lambda: clock[0], authorization_deadline=10)
    first.started = 0
    clock[0] = 8
    second = CaptionSession(lambda: None, clock=lambda: clock[0], authorization_deadline=10)
    second.started = 8
    assert not second.expired()
    clock[0] = 10
    assert first.expired() and second.expired()
    with pytest.raises(ValueError): CaptionSession(lambda: None, duration_seconds=301)


def test_transition_warning_remains_bounded_for_existing_multi_capture_contract():
    parent, snapshot, base, turns = source()
    captures, rows = [], []
    for i in range(20):
        capture = deepcopy(base[0]);capture.id = uuid4()
        capture.started_at += timedelta(seconds=15*i);capture.ended_at += timedelta(seconds=15*i)
        capture.recruiter_consented_at = capture.candidate_consented_at = capture.started_at
        captures.append(capture)
        for original in turns:
            row = deepcopy(original);row.id = uuid4();row.session_id = capture.id;rows.append(row)
    result = build_input(parent, snapshot, captures, rows)
    assert len(result.captures) == 20 and len(result.turns) == 40
    assert len(result.warning) <= 2000
    assert '14 additional transitions' in result.warning


def test_per_epoch_event_and_audio_bounds_remain_enforced():
    async def scenario():
        session, _, _ = await ready()
        try:
            session.sequence = 120
            with pytest.raises(ValueError, match='Caption limit'):
                await session._publish_caption('recruiter', 'Synthetic only', 0, 1)
            session.accepted_samples['candidate'] = session.duration_seconds * 16000
            await session.audio('candidate', bytes(3200))
            assert session.stopped
        finally:
            await session.stop()
    asyncio.run(scenario())
