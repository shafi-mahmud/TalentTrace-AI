"""Synthetic CV routing and privacy gates; no network/model inference."""
import asyncio,json
import httpx,pytest
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request
from app.core.config import Settings
from app.integrations.llm import screening_selection as cv,selection
from app.integrations.llm.candidate_profile import CandidateProviderError
from app.services.candidate_profile import validate_profile
from test_candidate_profile import source_document,interpretation
from test_ai_provider_selection import transport
from test_screening_matching import request as screening_input,semantic_result
from app.services.screening_matching import qualification_facts
from test_recruiter_records import workspace,client,login


def request(provider='',confirmed=False):
    headers=[(b'x-talenttrace-ai-provider',provider.encode())]
    if confirmed:headers.append((b'x-talenttrace-external-processing',b'confirmed'))
    return Request({'type':'http','headers':headers})

@pytest.mark.parametrize('provider,confirmed,status',[('',False,422),('groq',False,422),('groq',True,503),('ollama:unapproved',False,422),('ollama:qwen2.5:1.5b',False,503)])
def test_fail_closed_before_provider(provider,confirmed,status):
    with pytest.raises(HTTPException) as error:
        asyncio.run(cv.selected_screening(request(provider,confirmed),Settings(_env_file=None)))
    assert error.value.status_code==status

@pytest.mark.parametrize('model',selection.MODELS)
def test_both_stages_use_exact_local_model_with_existing_validation(monkeypatch,model):
    async def installed():return set(selection.MODELS)
    monkeypatch.setattr(cv,'installed_models',installed)
    document=source_document();calls=[]
    def handler(req):
        body=json.loads(req.content);calls.append(body)
        assert req.url.host=='127.0.0.1' and 'authorization' not in req.headers
        assert body['model']==model and not body['stream']
        content=interpretation(document).model_dump(mode='json') if len(calls)==1 else {'results':[semantic_result(identifier='python',status='not_found',evidence=[])]}
        return httpx.Response(200,json={'done':True,'model':model,'message':{'content':json.dumps(content)}})
    transport(monkeypatch,handler)
    async def run():
        service=await cv.selected_screening(request('ollama:'+model),Settings(_env_file=None,ollama_enabled=True))
        profile=validate_profile(document.upload_id,await service.profiles.extractor.extract(document),document)
        assert profile.qualifications.skills[0].value=='Python'
        supplied=screening_input(skills=('Django',))
        response=await service.workflow._semantic_matcher.match(supplied.criteria,qualification_facts(supplied))
        assert response.results[0].match_status=='not_found'
        assert service.ai_provenance=={'provider':'ollama','model':model,'external_processing_confirmed':False}
    asyncio.run(run());assert len(calls)==2

@pytest.mark.parametrize('bad',['malformed','schema'])
def test_bad_local_profile_never_falls_back(monkeypatch,bad):
    async def installed():return {selection.MODELS[0]}
    monkeypatch.setattr(cv,'installed_models',installed);calls=[]
    def handler(req):
        calls.append(req)
        return httpx.Response(200,json={'done':True,'model':selection.MODELS[0],'message':{'content':'invalid' if bad=='malformed' else '{"fabricated":true}'}})
    transport(monkeypatch,handler)
    async def run():
        service=await cv.selected_screening(request('ollama:'+selection.MODELS[0]),Settings(_env_file=None,ollama_enabled=True))
        with pytest.raises(CandidateProviderError):await service.profiles.extractor.extract(source_document())
    asyncio.run(run());assert len(calls)==1


def test_confirmed_groq_covers_both_stages():
    service=asyncio.run(cv.selected_screening(request('groq',True),Settings(_env_file=None,groq_api_key=SecretStr('synthetic-key'))))
    assert service.workflow._semantic_matcher.configuration==service.profiles.configuration
    assert service.ai_provenance['external_processing_confirmed'] is True


def test_owned_profile_route_requires_cloud_consent(workspace):
    _,users,password=workspace
    from uuid import uuid4
    async def run():
        async with client() as owner,client() as other,client() as anonymous:
            await login(owner,users[0],password);await login(other,users[1],password)
            job=(await owner.post('/api/v1/jobs',json={'job_title':'Synthetic CV routing'})).json()
            path=f'/api/v1/cv-uploads/{job["job_reference"]}/{uuid4()}/candidate-profiles'
            assert (await anonymous.post(path)).status_code==401
            assert (await other.post(path)).status_code==404
            assert (await owner.post(path)).status_code==422
            assert (await owner.post(path,headers={'X-TalentTrace-AI-Provider':'groq'})).status_code==422
    asyncio.run(run())


def test_provenance_preserves_score_contract():
    from test_candidate_scoring import scored
    from app.services.score_records import restore_candidate_score
    score,_,_=scored(['supported'],['skill'])
    payload=score.model_dump(mode='json');payload['_ai_provenance']={'provider':'ollama','model':selection.MODELS[0]}
    assert restore_candidate_score(payload)==score
    assert '_ai_provenance' in payload


def test_failed_screening_does_not_replace_saved_scores(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from app.api.routers import screening as route
    from app.services.batch_screening import BatchScreeningService
    from test_batch_screening import Profiles,candidate,snapshot,REFERENCE
    from app.schemas.batch_screening import ReviewedJobSnapshot
    from uuid import uuid4
    job=SimpleNamespace(revision=1)
    monkeypatch.setattr(route,'authorize_snapshot',AsyncMock(return_value=job))
    monkeypatch.setattr(route,'check_review',AsyncMock(return_value=False))
    monkeypatch.setattr(route,'private_settings',lambda _: Settings(_env_file=None))
    service=BatchScreeningService(Profiles([candidate(status='parsing_failed')]))
    monkeypatch.setattr(route,'selected_screening',AsyncMock(return_value=service))
    save=AsyncMock();monkeypatch.setattr(route,'persist_scores',save)
    result=asyncio.run(route.screen_batch(request(),REFERENCE,uuid4(),ReviewedJobSnapshot.model_validate(snapshot()),SimpleNamespace(id=uuid4()),None))
    assert result.scoring is None and result.candidates[0].result.status=='source_unavailable'
    save.assert_not_called()
