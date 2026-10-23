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
