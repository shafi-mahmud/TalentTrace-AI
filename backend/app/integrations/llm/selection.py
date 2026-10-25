"""JD-only selection. Fixed loopback endpoint, bounded allowlist, no fallback."""
import json
from types import SimpleNamespace as N
import httpx
from pydantic import SecretStr
from fastapi import HTTPException
from app.core.config import settings
from app.agents.jd.errors import GenerationProviderError, GenerationTimeoutError, MissingGenerationConfigurationError
from app.integrations.llm.groq import GroqJobDescriptionGenerator
from app.integrations.llm.recruiter_chat import GroqRecruiterInstructionInterpreter
from app.agents.jd.workflow import get_job_description_workflow
from app.services.recruiter_chat import RecruiterChatService

MODELS=('qwen2.5:1.5b','smollm2:360m-instruct-q4_K_M')
URL='http://127.0.0.1:11434'

async def installed_models():
    if not settings.ollama_enabled:return set()
    try:
        async with httpx.AsyncClient(timeout=2,trust_env=False,follow_redirects=False) as client:
            response=await client.get(URL+'/api/tags');response.raise_for_status()
            if len(response.content)>1048576:return set()
            return {r['name'] for r in response.json()['models'] if r.get('name') in MODELS}
    except Exception:return set()

async def provider_options():
    installed=await installed_models()
    return {'providers':[dict(id='groq',label='Groq API',available=bool(settings.groq_api_key and settings.groq_api_key.get_secret_value()),external=True),
        *[dict(id='ollama:'+model,label='Local · '+model,available=model in installed,external=False) for model in MODELS]]}

class OllamaClient:
    """Compatibility transport reusing existing interpretation/generation prompts and schemas."""
    def __init__(self,model,**kwargs):
        self.model=model;self.chat=N(completions=N(create=self.create))
    async def __aenter__(self):return self
    async def __aexit__(self,*args):pass
    async def create(self,**kwargs):
        try:
            async with httpx.AsyncClient(timeout=30,trust_env=False,follow_redirects=False) as client:
                response=await client.post(URL+'/api/chat',json={'model':self.model,'messages':kwargs['messages'],
                    'format':kwargs['response_format']['json_schema']['schema'],'stream':False,'keep_alive':0,
                    'options':{'temperature':0,'num_predict':kwargs['max_completion_tokens'],'num_ctx':4096}})
                response.raise_for_status()
                if len(response.content)>131072:raise ValueError()
                value=response.json()
                if value.get('done') is not True or value.get('model')!=self.model:raise ValueError()
                text=value['message']['content']
                if not isinstance(text,str) or not text.strip():raise ValueError()
                json.loads(text)
                return N(choices=[N(message=N(content=text))])
        except httpx.TimeoutException:raise GenerationTimeoutError('Local model timed out.') from None
        except Exception:raise GenerationProviderError('Local model returned no valid structured result.') from None

class OllamaGenerator(GroqJobDescriptionGenerator):
    def __init__(self,model,configuration):
        self.model=model
        super().__init__(configuration,client_factory=lambda **kwargs:OllamaClient(model,**kwargs))
    async def generate(self,*args,**kwargs):
        result=await super().generate(*args,**kwargs)
        return result.model_copy(update={'provider':'ollama','model':self.model})

async def selected_service(provider,external_confirmed):
    if provider=='groq':
        if not external_confirmed:raise HTTPException(422,'Confirm external JD processing first.')
        if not settings.groq_api_key:raise MissingGenerationConfigurationError('API provider unavailable.')
        return RecruiterChatService(GroqRecruiterInstructionInterpreter())
    model=provider.removeprefix('ollama:')
    if provider!='ollama:'+model or model not in MODELS or model not in await installed_models():
        raise MissingGenerationConfigurationError('Local model unavailable.')
    # The compatibility transports ignore this sentinel; it never leaves the machine.
    configuration=settings.model_copy(update={'groq_api_key':SecretStr('local-only-no-api-key')})
    interpreter=GroqRecruiterInstructionInterpreter(configuration,client_factory=lambda **kwargs:OllamaClient(model,**kwargs))
    return RecruiterChatService(interpreter,workflow_factory=lambda:get_job_description_workflow().with_generator(OllamaGenerator(model,configuration)))
