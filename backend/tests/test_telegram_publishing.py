"""Official Bot API contract tested with synthetic jobs and HTTPX MockTransport only."""
import asyncio,json,logging
from types import SimpleNamespace
from uuid import uuid4
import httpx,pytest
from fastapi import HTTPException
from pydantic import SecretStr,ValidationError
from app.core.config import Settings
from app.integrations.job_publishing.telegram import TelegramJobPublisher,PublicationContentError,publication_text
from app.integrations.job_publishing.mcp_client import PublicationUnavailable,PublicationFailed
from app.schemas.job_publication import RecruiterPublishRequest,PublicationResult
from app.api.routers import recruiter_chat as route
from app.core.auth import current_recruiter,database_session
from app.main import app
from test_job_publication import job,send
from test_recruiter_records import workspace,client,login,install_chat
from test_recruiter_chat import MESSAGE

TOKEN='123456:SYNTHETIC_ONLY_BOT_KEY_NOT_VALID'
CHANNEL='-1001234567890'

def config(**changes):
    return Settings(_env_file=None,telegram_publishing_enabled=True,telegram_bot_token=SecretStr(TOKEN),telegram_channel_id=SecretStr(CHANNEL),**changes)

def request(**changes):
    r=RecruiterPublishRequest.model_validate({**job(),'destination':'telegram',**changes})
    r._job_reference='TT-JOB-0123456789ABCDEF'
    return r


def test_disabled_and_missing_credentials_never_connect():
    def forbidden(req):pytest.fail('Unconfigured provider must not connect')
    for c in [Settings(_env_file=None),Settings(_env_file=None,telegram_publishing_enabled=True),config().model_copy(update={'telegram_publishing_enabled':False}),config().model_copy(update={'telegram_channel_id':SecretStr('https://untrusted.invalid')})]:
        with pytest.raises(PublicationUnavailable):asyncio.run(TelegramJobPublisher(c,transport=httpx.MockTransport(forbidden)).publish(request()))


def test_confirmed_exact_channel_receipt_and_token_redaction(caplog):
    calls=[];r=request();text=publication_text(r)
    def handler(req):
        calls.append(req);body=json.loads(req.content)
        assert req.url.host=='api.telegram.org' and req.url.path.endswith('/sendMessage')
        assert body=={'chat_id':CHANNEL,'text':text,'link_preview_options':{'is_disabled':True},'allow_paid_broadcast':False}
        assert r._job_reference in text and 'Python' in text and 'Responsibilities' in text
        return httpx.Response(200,json={'ok':True,'result':{'message_id':42,'chat':{'id':int(CHANNEL),'type':'channel'},'text':text}})
    with caplog.at_level(logging.INFO):
        receipt=asyncio.run(TelegramJobPublisher(config(),transport=httpx.MockTransport(handler)).publish(r))
        logging.getLogger('httpcore.http11').info('POST /bot%s/sendMessage',TOKEN)
    assert receipt==PublicationResult(destination='telegram',status='published',external_id='42')
    assert TOKEN not in caplog.text and len(calls)==1

@pytest.mark.parametrize('failure',['timeout','redirect','http','rejected','wrong_channel','wrong_type','missing_id','bool_id','wrong_text','malformed'])
def test_uncertain_or_failed_response_never_claims_success_or_retries(failure):
    calls=[];r=request()
    def handler(req):
        calls.append(req)
        if failure=='timeout':raise httpx.ReadTimeout('PRIVATE')
        if failure=='redirect':return httpx.Response(302,headers={'location':'https://untrusted.invalid'})
        if failure=='http':return httpx.Response(500,json={'description':TOKEN})
        if failure=='malformed':return httpx.Response(200,content=b'not-json')
        body={'ok':True,'result':{'message_id':42,'chat':{'id':int(CHANNEL),'type':'channel'},'text':publication_text(r)}}
        if failure=='rejected':body['ok']=False
        if failure=='wrong_channel':body['result']['chat']['id']=-1009999999999
        if failure=='wrong_type':body['result']['chat']['type']='private'
        if failure=='missing_id':body['result'].pop('message_id')
        if failure=='bool_id':body['result']['message_id']=True
        if failure=='wrong_text':body['result']['text']='Wrong job'
        return httpx.Response(200,json=body)
    with pytest.raises(PublicationFailed) as error:
        asyncio.run(TelegramJobPublisher(config(),transport=httpx.MockTransport(handler)).publish(r))
    assert len(calls)==1 and TOKEN not in str(error.value) and 'PRIVATE' not in str(error.value)


def test_oversized_content_fails_before_delivery_without_truncation():
    r=request(summary='x'*3000,responsibilities=['x'*300]*10)
    with pytest.raises(PublicationContentError):asyncio.run(TelegramJobPublisher(config(),transport=httpx.MockTransport(lambda req:pytest.fail('No call'))).publish(r))
    r._job_reference=None
    with pytest.raises(PublicationContentError):publication_text(r)


def test_destination_and_credentials_cannot_be_overridden():
    for changes in [{'destination':'linkedin'},{'bot_token':TOKEN},{'channel_id':CHANNEL},{'endpoint':'https://untrusted.invalid'}]:
        with pytest.raises(ValidationError):request(**changes)
    assert 'destination' not in request().mcp_job()
    with pytest.raises(ValidationError):PublicationResult(destination='discord',status='published',external_id='42')

@pytest.fixture
def api(monkeypatch):
    previous=dict(app.dependency_overrides);route.publication_attempts.clear()
    async def user():return SimpleNamespace(id=uuid4())
    # Stable synthetic recruiter identity is essential for duplicate fencing.
    recruiter=SimpleNamespace(id=uuid4())
    async def stable_user():return recruiter
    async def db():yield None
    app.dependency_overrides[current_recruiter]=stable_user;app.dependency_overrides[database_session]=db
    async def authorize(session,owner,req):req._job_reference='TT-JOB-0123456789ABCDEF'
    monkeypatch.setattr(route,'authorize_publication',authorize)
    yield
    route.publication_attempts.clear();app.dependency_overrides.clear();app.dependency_overrides.update(previous)


def test_independent_destinations_partial_success_and_uncertain_duplicate_fence(api,monkeypatch):
    calls=[]
    class Discord:
        async def publish(self,req):calls.append('discord');return PublicationResult(destination='discord',status='published',external_id='123456789012345678')
    class Telegram:
        async def publish(self,req):calls.append('telegram');raise PublicationFailed('PRIVATE')
    monkeypatch.setattr(route,'get_job_publisher',Discord);monkeypatch.setattr(route,'get_telegram_publisher',Telegram)
    async def run():
        assert (await send(job())).status_code==200
        first=await send({**job(),'destination':'telegram'})
        assert first.status_code==502 and 'PRIVATE' not in first.text
        assert (await send({**job(),'destination':'telegram'})).status_code==409
        assert (await send(job())).status_code==200
        async def denied(*args):raise HTTPException(404,'Job not found')
        monkeypatch.setattr(route,'authorize_publication',denied)
        assert (await send(job())).status_code==404
        assert (await send({**job(),'destination':'telegram'})).status_code==404
    asyncio.run(run());assert calls==['discord','telegram']


def test_telegram_success_and_destination_mismatch(api,monkeypatch):
    class Telegram:
        async def publish(self,req):return PublicationResult(destination='telegram',status='published',external_id='42')
    monkeypatch.setattr(route,'get_telegram_publisher',Telegram)
    async def run():
        a=await send({**job(),'destination':'telegram'});b=await send({**job(),'destination':'telegram'})
        assert a.status_code==b.status_code==200 and a.json()==b.json()
        route.publication_attempts.clear()
        monkeypatch.setattr(route,'get_job_publisher',Telegram)
        assert (await send(job())).status_code==502
    asyncio.run(run())


def test_real_job_ownership_stale_preview_and_original_reference(workspace,monkeypatch):
    _,users,password=workspace;install_chat(monkeypatch);route.publication_attempts.clear();calls=[]
    class Telegram:
        async def publish(self,req):
            calls.append(req)
            return PublicationResult(destination='telegram',status='published',external_id='42')
    monkeypatch.setattr(route,'get_telegram_publisher',Telegram)
    async def run():
        async with client() as owner,client() as foreign,client() as anonymous:
            await login(owner,users[0],password);await login(foreign,users[1],password)
            generated=await owner.post('/api/v1/recruiter-chat',json={'message':MESSAGE})
            assert generated.status_code==200
            data=generated.json();d=data['job_description_result']['job_description']
            payload={k:d[k] for k in ('title','summary','responsibilities','required_skills','preferred_skills','qualifications')}
            payload.update(job_id=data['draft_id'],destination='telegram')
            path='/api/v1/recruiter-chat/publish'
            assert (await anonymous.post(path,json=payload)).status_code==401
            assert (await foreign.post(path,json=payload)).status_code==404
            assert (await owner.post(path,json={**payload,'title':'Stale title'})).status_code==409
            assert (await owner.post(path,json={**payload,'job_reference':'FORGED'})).status_code==422
            assert (await owner.post(path,json=payload)).status_code==200
            assert calls[0]._job_reference==data['job_reference']
            assert (await owner.post(path,json=payload)).status_code==200
            assert (await foreign.post(path,json=payload)).status_code==404
    asyncio.run(run());assert len(calls)==1
    route.publication_attempts.clear()
