"""Mock-only provider routing; no model or provider connections."""
import asyncio,json
import httpx
import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from app.core.config import Settings
from app.agents.jd.errors import GenerationProviderError,GenerationTimeoutError,MissingGenerationConfigurationError
from app.integrations.llm import selection as module
from app.api.routers import recruiter_chat
from test_recruiter_records import workspace,client,login,install_chat
from test_recruiter_chat import MESSAGE
from test_groq_job_description import request_contract,policy_context,valid_provider_json


def transport(monkeypatch,handler):
    real=httpx.AsyncClient
    monkeypatch.setattr(module.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(handler),**kwargs))


def test_local_generator_uses_only_loopback_and_strict_schema(monkeypatch):
    seen=[]
    def handler(request):
        assert str(request.url)=='http://127.0.0.1:11434/api/chat'
        body=json.loads(request.content);seen.append(body)
        assert body['model']=='qwen2.5:1.5b' and body['stream'] is False and body['keep_alive']==0
        return httpx.Response(200,json={'done':True,'model':body['model'],'message':{'content':valid_provider_json(policy_context()[0].chunk.metadata.citation_id)}})
    transport(monkeypatch,handler)
    config=Settings(_env_file=None,groq_api_key=SecretStr('local-only'))
    result=asyncio.run(module.OllamaGenerator('qwen2.5:1.5b',config).generate(request_contract(),policy_context()))
    assert result.provider=='ollama' and result.model=='qwen2.5:1.5b' and len(seen)==1


@pytest.mark.parametrize('failure',['timeout','malformed','schema','wrong_model'])
def test_local_errors_never_fallback(monkeypatch,failure):
    calls=[]
    def handler(request):
        calls.append(request)
        if failure=='timeout':raise httpx.ReadTimeout('PRIVATE')
        return httpx.Response(200,json={'done':True,'model':'wrong' if failure=='wrong_model' else 'qwen2.5:1.5b',
            'message':{'content':'invalid-json' if failure=='malformed' else '{}'}})
    transport(monkeypatch,handler)
    config=Settings(_env_file=None,groq_api_key=SecretStr('local-only'))
    with pytest.raises(GenerationTimeoutError if failure=='timeout' else GenerationProviderError) as error:
        asyncio.run(module.OllamaGenerator('qwen2.5:1.5b',config).generate(request_contract(),policy_context()))
    assert 'PRIVATE' not in str(error.value) and len(calls)==1


def test_discovery_allowlist_and_explicit_external_consent(monkeypatch):
    monkeypatch.setattr(module,'settings',Settings(_env_file=None,ollama_enabled=True))
    transport(monkeypatch,lambda request:httpx.Response(200,json={'models':[{'name':'qwen2.5:1.5b'},{'name':'unapproved'}]}))
    rows=asyncio.run(module.provider_options())['providers']
    assert [r['id'] for r in rows if r['available']]==['ollama:qwen2.5:1.5b']
    assert not any('url' in r or 'key' in r for r in rows)
    with pytest.raises(HTTPException):asyncio.run(module.selected_service('groq',False))
    with pytest.raises(MissingGenerationConfigurationError):asyncio.run(module.selected_service('ollama:unapproved',False))


def test_authenticated_conversations_pin_selection_and_deny_foreign_owner(workspace,monkeypatch):
    _,users,password=workspace;install_chat(monkeypatch)
    monkeypatch.setattr(module,'settings',Settings(_env_file=None))
    async def selected(*args):return recruiter_chat.RecruiterChatService(recruiter_chat.get_recruiter_interpreter())
    monkeypatch.setattr(module,'selected_service',selected)
    async def run():
        async with client() as owner,client() as foreign,client() as anonymous:
            assert (await anonymous.get('/api/v1/recruiter-chat/providers')).status_code==401
            await login(owner,users[0],password);await login(foreign,users[1],password)
            assert (await owner.get('/api/v1/recruiter-chat/providers')).status_code==200
            first=await owner.post('/api/v1/recruiter-chat',json={'message':MESSAGE,'ai_provider':'ollama:qwen2.5:1.5b'})
            assert first.status_code==200
            conversation=first.json()['conversation_id']
            assert (await foreign.post('/api/v1/recruiter-chat',json={'message':MESSAGE,'conversation_id':conversation,'ai_provider':'ollama:qwen2.5:1.5b'})).status_code==404
            assert (await owner.post('/api/v1/recruiter-chat',json={'message':MESSAGE,'conversation_id':conversation})).status_code==409
            assert (await owner.post('/api/v1/recruiter-chat',json={'message':MESSAGE,'ai_provider':'http://private.invalid','api_key':'PRIVATE'})).status_code==422
    asyncio.run(run())


def test_local_interpretation_uses_same_fixed_model_without_cloud(monkeypatch):
    from test_recruiter_chat import extracted_data
    from app.schemas.recruiter_chat import RecruiterChatRequest
    from app.integrations.llm.recruiter_chat import GroqRecruiterInstructionInterpreter
    calls=[]
    def handler(request):
        body=json.loads(request.content);calls.append(body)
        assert request.url.host=='127.0.0.1' and 'authorization' not in request.headers
        return httpx.Response(200,json={'done':True,'model':'qwen2.5:1.5b','message':{'content':json.dumps(extracted_data())}})
    transport(monkeypatch,handler)
    config=Settings(_env_file=None,groq_api_key=SecretStr('local-only'))
    interpreter=GroqRecruiterInstructionInterpreter(config,client_factory=lambda **kw:module.OllamaClient('qwen2.5:1.5b',**kw))
    result=asyncio.run(interpreter.interpret(RecruiterChatRequest(message=MESSAGE)))
    assert result.intent=='create_job_description' and len(calls)==1
