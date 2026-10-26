"""Real authenticated persistence/refinement; synthetic interpreter and SQL double."""
import asyncio
from copy import deepcopy

import httpx
import pytest
from app.api.routers import recruiter_chat as route
from app.services.recruiter_chat import RecruiterChatService
from app.schemas.recruiter_chat import RecruiterInterpretation
from app.schemas.recruiter_chat import RecruiterChatResponse
from pydantic import TypeAdapter
from app.db.models.recruiter import JobProfile
from test_recruiter_chat import MESSAGE, extracted_data, empty_extraction, evidence, RecordingWorkflow
from test_recruiter_records import workspace, client, login
from app.services.recruiter_chat import grounded_value
from app.schemas.recruiter_chat import TextEvidence

REVISION = "Change the required experience to 3 years and add Docker as a preferred skill."


def test_same_owned_job_revision_rehydrates_and_invalidates_confirmation(workspace, monkeypatch):
    database, users, password = workspace
    workflow = RecordingWorkflow()
    class Interpreter:
        async def interpret(self, request, context=None):
            value = empty_extraction(minimum_experience_years=evidence(3, "Change the required experience to 3 years"),
                preferred_skills=[evidence("Docker")]) if request.message == REVISION else extracted_data()
            return RecruiterInterpretation.model_validate(value)
    monkeypatch.setattr(route, 'get_recruiter_interpreter', Interpreter)
    monkeypatch.setattr(route, 'RecruiterChatService', lambda interpreter: RecruiterChatService(interpreter, workflow_factory=lambda: workflow))
    async def denied(*args, **kwargs): pytest.fail('External provider request forbidden')
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', denied)
    async def scenario():
        async with client() as owner, client() as foreign:
            await login(owner, users[0], password); await login(foreign, users[1], password)
            first = (await owner.post('/api/v1/recruiter-chat', json={'message': MESSAGE})).json()
            other = (await owner.post('/api/v1/recruiter-chat', json={'message': MESSAGE})).json()
            assert first['draft_id'] != other['draft_id']
            def record(row):
                return {column.name: deepcopy(getattr(row, column.name)) for column in row.__table__.columns}
            other_before = record(next(j for j in database[JobProfile] if str(j.id) == other['draft_id']))
            approval = await owner.put(f"/api/v1/jobs/{first['draft_id']}/criteria", json={
                'revision': 1, 'confirmed': True, 'criteria': first['screening_suggestions']['criteria']})
            assert approval.status_code == 200
            payload = {'message': REVISION, 'conversation_id': first['conversation_id']}
            assert (await foreign.post('/api/v1/recruiter-chat', json=payload)).status_code == 404
            revised = await owner.post('/api/v1/recruiter-chat', json=payload)
            assert revised.status_code == 200
            reply = revised.json()
            assert reply['status'] == 'jd_generated'
            assert reply['draft_id'] == first['draft_id'] and reply['job_reference'] == first['job_reference']
            assert reply['job_revision'] == 3  # Generation 1, confirmation 2, refinement 3.
            assert reply['conversation_id'] == first['conversation_id']
            assert workflow.requests[-1].minimum_experience_years == 3
            assert workflow.requests[-1].preferred_skills == ['Docker']
            assert workflow.requests[-1].required_skills == ['Python', 'FastAPI']
            job = (await owner.get('/api/v1/jobs')).json()
            updated = next(j for j in job if j['id'] == first['draft_id'])
            assert updated['revision'] == 3 and updated['snapshot'] is None
            assert any(c['description'] == 'Docker' for c in updated['suggestions']['criteria'])
            assert record(next(j for j in database[JobProfile] if str(j.id) == other['draft_id'])) == other_before
            restored = (await owner.get(f"/api/v1/conversations/{first['conversation_id']}")).json()
            adapter = TypeAdapter(RecruiterChatResponse)
            assert adapter.validate_python(restored['turns'][-1]['reply']) == adapter.validate_python(reply)
            assert len(database[JobProfile]) == 2
            assert (await foreign.get(f"/api/v1/conversations/{first['conversation_id']}")).status_code == 404
    asyncio.run(scenario())


@pytest.mark.parametrize('message', [
    'Add Docker as a preferred skill without changing required skills.',
    'Add Docker as a preferred skill without changing the required skills.',
])
@pytest.mark.parametrize('full_sentence_evidence', [False, True])
def test_add_preferred_preserves_both_lists_and_saved_identity(workspace, monkeypatch, message, full_sentence_evidence):
    database, users, password = workspace
    workflow = RecordingWorkflow()
    initial_message = MESSAGE + ' Preferred skill: Git.'

    class Interpreter:
        async def interpret(self, request, context=None):
            data = extracted_data()
            data['requirements']['preferred_skills'] = [evidence('Git')]
            if request.message == message:
                data = empty_extraction(preferred_skills=[evidence('Docker', message if full_sentence_evidence else 'Docker')])
            return RecruiterInterpretation.model_validate(data)

    monkeypatch.setattr(route, 'get_recruiter_interpreter', Interpreter)
    monkeypatch.setattr(route, 'RecruiterChatService', lambda interpreter: RecruiterChatService(interpreter, workflow_factory=lambda: workflow))

    async def scenario():
        async with client() as owner:
            await login(owner, users[0], password)
            first = (await owner.post('/api/v1/recruiter-chat', json={'message':initial_message})).json()
            approved = await owner.put(f"/api/v1/jobs/{first['draft_id']}/criteria", json={
                'revision':1, 'confirmed':True, 'criteria':first['screening_suggestions']['criteria']})
            assert approved.status_code == 200
            response = await owner.post('/api/v1/recruiter-chat', json={'message':message,'conversation_id':first['conversation_id']})
            assert response.status_code == 200
            revised = response.json()
            assert revised['status'] == 'jd_generated'
            assert revised['job_reference'] == first['job_reference']
            assert revised['draft_id'] == first['draft_id']
            assert revised['job_revision'] == 3
            assert workflow.requests[-1].required_skills == ['Python','FastAPI']
            assert workflow.requests[-1].preferred_skills == ['Git','Docker']
        async with client() as refreshed:
            await login(refreshed, users[0], password)
            job = (await refreshed.get('/api/v1/jobs')).json()[0]
            assert job['snapshot'] is None and job['revision'] == 3
            saved = (await refreshed.get('/api/v1/conversations/'+first['conversation_id'])).json()
            adapter = TypeAdapter(RecruiterChatResponse)
            assert adapter.validate_python(saved['turns'][-1]['reply']) == adapter.validate_python(revised)
            assert len(database[JobProfile]) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize('field,message', [
    ('required_skills', 'Docker is not required.'),
    ('preferred_skills', 'Do not add Docker.'),
    ('preferred_skills', 'Do not add Docker without changing required skills.'),
    ('preferred_skills', 'Add Docker without changing required skills but do not add Docker.'),
    ('preferred_skills', 'Add Docker without changing Docker.'),
])
def test_preservation_exception_does_not_accept_negated_or_ambiguous_skills(field, message):
    with pytest.raises(ValueError):
        grounded_value(field, TextEvidence(value='Docker',evidence='Docker'), message)
