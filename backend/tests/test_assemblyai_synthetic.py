"""Offline fake WSS plus actual deterministic graph; no provider requests."""
import asyncio,json,time
from uuid import uuid4
import pytest
from pydantic import SecretStr
from app.integrations.stt.assemblyai_synthetic import AssemblyAISyntheticStream,fixture_pcm
from app.services.synthetic_streaming_captions import SyntheticStreamingCaptions
from app.core.config import Settings,ConfigurationError
from app.services.copilot_live import LiveBridge
from test_copilot_delivery import offline,runtime,consent
QUESTION='In Python, are lists mutable? Explain how append changes a list and how indexing retrieves an element.'
ANSWER='Python lists are mutable ordered sequences. The append method adds one item to the end of the existing list. Indexing starts at zero. A negative index, such as minus one, retrieves the last element.'
class Socket:
 def __init__(self,conflict=False,acknowledge=True,error=False,text=QUESTION):
  self.text=text;self.q=asyncio.Queue();self.sent=[];self.closed=False;self.conflict=conflict;self.acknowledge=acknowledge;self.error=error
  self.q.put_nowait(json.dumps({'type':'Begin','configuration':{'model':'universal-streaming-english'}}))
 def __aiter__(self):return self
 async def __anext__(self):return await self.q.get()
 async def send(self,value):
  self.sent.append(value)
  if isinstance(value,bytes):return
  kind=json.loads(value)['type']
  if kind=='ForceEndpoint':
   if self.error:self.q.put_nowait(json.dumps({'type':'Error','error':'private'}));return
   for m in [dict(type='Turn',turn_order=0,end_of_turn=False,transcript='partial'),dict(type='Turn',turn_order=0,end_of_turn=True,turn_is_formatted=True,transcript=self.text),dict(type='Turn',turn_order=0,end_of_turn=True,turn_is_formatted=True,transcript='conflict' if self.conflict else self.text)]:self.q.put_nowait(json.dumps(m))
  if kind=='Terminate' and self.acknowledge:self.q.put_nowait(json.dumps({'type':'Termination','audio_duration_seconds':7,'session_duration_seconds':10}))
 async def close(self):self.closed=True
async def no_sleep(_):await asyncio.sleep(0)
def test_fixtures():
 assert len(fixture_pcm('recruiter'))==232218
 assert len(fixture_pcm('candidate'))==472060
 with pytest.raises(ValueError):fixture_pcm('../private')
def test_dedup_final_only_and_exact_audio():
 async def run():
  ws=Socket();calls=[]
  async def connect(url,**kw):calls.append(url);return ws
  p=AssemblyAISyntheticStream('recruiter',SecretStr('fake'),connector=connect,sleep=no_sleep)
  assert await p.run()==QUESTION
  assert len(calls)==1 and p.termination_confirmed and ws.closed
  assert b''.join(v for v in ws.sent if isinstance(v,bytes))==fixture_pcm('recruiter')
  assert sum(isinstance(v,str) and json.loads(v)['type']=='Terminate' for v in ws.sent)==1
  with pytest.raises(ValueError):await p.run()
 asyncio.run(run())
@pytest.mark.parametrize('mode',['conflict','network','no_ack'])
def test_failure_terminates(mode):
 async def run():
  ws=Socket(conflict=mode=='conflict',acknowledge=mode!='no_ack',error=mode=='network')
  async def connect(*a,**kw):return ws
  async def sleep(_):p.deadline=time.monotonic()+.02;await asyncio.sleep(0)
  p=AssemblyAISyntheticStream('candidate',SecretStr('fake'),connector=connect,sleep=sleep)
  with pytest.raises((ValueError,TimeoutError)):await p.run()
  assert p.terminate_sent and ws.closed
  if mode=='no_ack':assert not p.termination_confirmed
 asyncio.run(run())
def test_cancel_terminates():
 async def run():
  ws=Socket();entered=asyncio.Event()
  async def connect(*a,**kw):return ws
  async def sleep(_):entered.set();await asyncio.Event().wait()
  p=AssemblyAISyntheticStream('candidate',SecretStr('fake'),connector=connect,sleep=sleep)
  task=asyncio.create_task(p.run());await entered.wait();await p.close();task.cancel()
  with pytest.raises(asyncio.CancelledError):await task
  assert p.terminate_sent and p.termination_confirmed and ws.closed
 asyncio.run(run())
def test_disabled_and_guarded_configuration():
 assert not Settings(_env_file=None).assemblyai_synthetic_enabled
 with pytest.raises(ConfigurationError):Settings(_env_file=None,assemblyai_synthetic_enabled=True)
 with pytest.raises(ConfigurationError):Settings(_env_file=None,assemblyai_synthetic_enabled=True,environment='production',assemblyai_api_key='fake',assemblyai_synthetic_interview_id=uuid4())
async def setup(runtime,slow=False):
 manager,access,clock=runtime;events=[];workers=[];entered=asyncio.Event();release=asyncio.Event()
 class Worker(AssemblyAISyntheticStream):
  def __init__(self,role):
   self.socket=Socket(text=QUESTION if role=='recruiter' else ANSWER)
   async def connect(*a,**kw):return self.socket
   super().__init__(role,SecretStr('fake'),connector=connect,sleep=no_sleep);workers.append(self)
  async def run(self):
   entered.set()
   if slow:await release.wait()
   result=await super().run();self.audio_started_at=clock[0];clock[0]+=1;self.audio_ended_at=clock[0];return result
 s=SyntheticStreamingCaptions(Worker,access.interview);s.clock=lambda:clock[0]
 async def send(v):events.append(v)
 for role in ('recruiter','candidate'):
  await s.connect(role,send)
  async def check():pass
  s.authorization_checks[role]=check
 await s.approve('recruiter');assert not workers
 await s.approve('candidate');assert not workers
 s.started_wall=100
 async def authorize():return access
 b=LiveBridge(access.interview,s.caption_run_id,manager,authorize,settle=.01);s.assistant=b
 manager.prepare(access,caption_run_id=s.caption_run_id)
 consent(manager,access,'recruiter');consent(manager,access,'candidate');clock[0]=106
 return s,b,events,workers,entered,release
def test_authorized_bridge_suggestion_private_delivery_and_withdrawal(runtime):
 async def run():
  manager,access,clock=runtime;s,b,events,workers,_,_=await setup(runtime)
  with pytest.raises(ValueError):await s.start_replay('candidate')
  with pytest.raises(ValueError):await s.audio('candidate',b'private microphone')
  await s.start_replay('recruiter');await s.replay;clock[0]+=4
  if b.task:await asyncio.wait_for(asyncio.shield(b.task),3)
  assert [r.role for r in b.records]==['recruiter','candidate']
  assert all(r.source.caption_run_id==s.caption_run_id for r in b.records)
  assert s.complete and s.accepted_samples==s.processed_samples
  assert manager.view(access,recruiter=True)['suggestion'] is not None
  assert 'suggestion' not in manager.view(access)
  with pytest.raises(ValueError):await s.start_replay('recruiter')
  await s.stop();assert all(w.closed for w in workers) and manager.view(access)['status']=='withdrawn'
 asyncio.run(run())
def test_withdraw_cancels_delayed_result(runtime):
 async def run():
  s,b,events,workers,entered,release=await setup(runtime,slow=True)
  await s.start_replay('recruiter');await entered.wait();await s.stop();release.set()
  assert s.replay.done() and all(w.closed for w in workers)
  assert not b.records and not any(e['kind']=='caption' for e in events)
 asyncio.run(run())
def test_requires_assistant_consent(runtime):
 async def run():
  manager,access,_=runtime;s,b,events,workers,_,_=await setup(runtime);manager.invalidate(access.interview)
  with pytest.raises(ValueError):await s.start_replay('recruiter')
  assert not workers;await s.stop()
 asyncio.run(run())
def test_expiry_no_provider(runtime):
 async def run():
  _,_,clock=runtime;s,b,events,workers,_,_=await setup(runtime);clock[0]+=121
  with pytest.raises(ValueError):await s.start_replay('recruiter')
  assert not workers;await s.stop()
 asyncio.run(run())


def test_f11_withdrawal_cancels_stream(runtime):
 async def run():
  manager,access,clock=runtime;s,b,events,workers,entered,release=await setup(runtime,slow=True)
  await s.start_replay('recruiter');await entered.wait();manager.invalidate(access.interview)
  await asyncio.wait_for(s.replay,2);await s.stop()
  assert not any(e['kind']=='caption' for e in events)
  assert len(workers)==1 and all(w.closed for w in workers)
 asyncio.run(run())

def test_normal_finish_waits_for_replay(runtime):
 async def run():
  s,b,events,workers,entered,release=await setup(runtime,slow=True)
  await s.start_replay('recruiter');await entered.wait();await s.request_finish('candidate')
  assert not s.stopped;release.set();await asyncio.wait_for(s.finalizer,3)
  assert s.complete and s.stopped and all(w.termination_confirmed for w in workers)
  assert any(e['kind']=='synthetic-termination' and e['confirmed'] for e in events)
 asyncio.run(run())

def test_fixture_tamper_rejected(monkeypatch,tmp_path):
 from app.integrations.stt import assemblyai_synthetic as module
 (tmp_path/'recruiter.wav').write_bytes(b'not approved audio')
 monkeypatch.setattr(module,'FIXTURES',tmp_path)
 with pytest.raises(ValueError):fixture_pcm('recruiter')

@pytest.mark.parametrize('wrong_interview,unauthorized,browser_audio',[(True,False,False),(False,True,False),(False,False,True)])
def test_socket_boundary_no_provider(monkeypatch,wrong_interview,unauthorized,browser_audio):
 from datetime import datetime,timedelta,timezone
 from fastapi import HTTPException
 from fastapi.testclient import TestClient
 from starlette.websockets import WebSocketDisconnect
 from app.main import app
 from app.api.routers import interview_captions as route
 from app.integrations.stt import assemblyai_synthetic as module
 key=uuid4()
 monkeypatch.setattr(route,'settings',route.settings.model_copy(update={
  'livekit_synthetic_demo_enabled':True,'assemblyai_synthetic_enabled':True,
  'assemblyai_synthetic_interview_id':uuid4() if wrong_interview else key,'local_caption_model_path':None}))
 async def authorize(*a):
  if unauthorized:raise HTTPException(401,'private')
  return key,'candidate',uuid4(),datetime.now(timezone.utc)+timedelta(minutes=10)
 monkeypatch.setattr(route,'authorize',authorize)
 async def forbidden(*a,**kw):pytest.fail('Must not connect external provider')
 monkeypatch.setattr(module,'connect',forbidden)
 with TestClient(app) as client:
  if wrong_interview or unauthorized:
   with pytest.raises(WebSocketDisconnect):
    with client.websocket_connect('/api/v1/interview-access/captions',headers={'origin':'http://localhost:5173'}):pass
  else:
   with client.websocket_connect('/api/v1/interview-access/captions',headers={'origin':'http://localhost:5173'}) as ws:
    assert ws.receive_json()=={'kind':'waiting'};ws.send_bytes(bytes(3200))
    assert ws.receive_json()['kind']=='synthetic-termination'
    assert ws.receive_json()=={'kind':'stopped'}
 assert not route.sessions

@pytest.mark.parametrize('change',['authorization','expiry'])
def test_changed_authorization_during_stream_stops_without_candidate_connection(runtime,change):
 async def run():
  s,b,events,workers,entered,release=await setup(runtime,slow=True)
  await s.start_replay('recruiter');await entered.wait()
  async def denied():raise ValueError('revoked')
  if change=='authorization':s.authorization_checks['candidate']=denied
  else:runtime[2][0]+=121
  await asyncio.wait_for(s.replay,2);await s.stop()
  assert len(workers)==1 and workers[0].closed
  assert not any(e['kind']=='caption' for e in events)
 asyncio.run(run())

def test_disconnect_cleanup_tolerates_failed_browser_send(runtime):
 async def run():
  s,b,events,workers,entered,release=await setup(runtime,slow=True)
  await s.start_replay('recruiter');await entered.wait()
  async def disconnected(v):raise ConnectionError('closed')
  s.peers['candidate']=disconnected
  await s.stop()
  assert s.replay.done() and workers[0].closed
 asyncio.run(run())


def test_transport_failure_attempts_termination_and_never_retries():
 async def run():
  class Broken(Socket):
   async def send(self,value):
    if isinstance(value,bytes):raise ConnectionError('private transport details')
    await super().send(value)
  ws=Broken();calls=[]
  async def connect(*a,**kw):calls.append(1);return ws
  p=AssemblyAISyntheticStream('recruiter',SecretStr('fake'),connector=connect,sleep=no_sleep)
  with pytest.raises(ConnectionError):await p.run()
  assert len(calls)==1 and p.terminate_sent and ws.closed
 asyncio.run(run())

def test_process_budget_survives_caption_session_replacement(runtime):
 async def run():
  s,b,events,workers,_,_=await setup(runtime)
  await s.start_replay('recruiter');await s.replay;await s.stop()
  replacement,_,_,workers2,_,_=await setup(runtime)
  with pytest.raises(ValueError):await replacement.start_replay('recruiter')
  assert not workers2;await replacement.stop()
 asyncio.run(run())


@pytest.mark.parametrize('provider_error',[True,False])
def test_receiver_failure_or_early_termination_stops_audio_immediately(provider_error):
 async def run():
  class EarlyFailure(Socket):
   async def send(self,value):
    await super().send(value)
    if isinstance(value,bytes):
     message={'type':'Error','error':'private'} if provider_error else {'type':'Termination'}
     self.q.put_nowait(json.dumps(message))
  ws=EarlyFailure()
  async def connect(*a,**kw):return ws
  p=AssemblyAISyntheticStream('candidate',SecretStr('fake'),connector=connect,sleep=no_sleep)
  with pytest.raises(ValueError):await p.run()
  assert len([v for v in ws.sent if isinstance(v,bytes)])==1
  assert p.terminate_sent and ws.closed
 asyncio.run(run())
