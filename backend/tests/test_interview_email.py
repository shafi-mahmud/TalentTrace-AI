import asyncio,smtplib
from datetime import datetime,timezone
from types import SimpleNamespace as N
import pytest
from pydantic import SecretStr
from app.core.config import Settings
from app.services.interview_email import dispatch,template,recipient,ready,finish_attempt

def config():return Settings(_env_file=None,interview_email_enabled=True,environment='development',livekit_synthetic_demo_enabled=True,interview_email_sender='sender@synthetic.invalid',interview_email_recipients=['approved@synthetic.invalid'],interview_public_origin='https://demo.example.test',interview_smtp_host='smtp.example.test',interview_smtp_username=SecretStr('synthetic'),interview_smtp_password=SecretStr('synthetic'))
class Fake:
 def __init__(self,error=None):self.error=error;self.messages=[]
 def send(self,*args):
  if self.error:raise self.error
  self.messages.append(args)

def test_templates_and_actual_joining_path():
 c=config();token='A'*43
 subject,body=template(c,'scheduling',token);assert '/interview-schedule#schedule=' in body
 _,body=template(c,'confirmation',token,N(scheduled_at=datetime(2026,10,15,2,tzinfo=timezone.utc),duration_minutes=60))
 assert '15 October 2026' in body and '08:00–09:00 Asia/Dhaka' in body and '60 minutes' in body
 assert '/interview-join#invite=' in body and '/interview-schedule' not in body

def test_allowlist_and_disabled_transport():
 c=config()
 from fastapi import HTTPException
 for value in ['unapproved@synthetic.invalid','bad\r\n@example.com','person@example.com']:
  with pytest.raises(HTTPException):recipient(c,value)
 f=Fake();c.interview_email_enabled=False
 assert asyncio.run(dispatch(c,'approved@synthetic.invalid','scheduling','A'*43,transport=f))=='not_configured'
 assert f.messages==[]

@pytest.mark.parametrize('error,status',[(None,'accepted'),(TimeoutError('PRIVATE'),'uncertain'),(smtplib.SMTPServerDisconnected('PRIVATE'),'uncertain'),(smtplib.SMTPAuthenticationError(535,b'PRIVATE'),'failed')])
def test_fake_delivery_states_no_retries(error,status):
 f=Fake(error);result=asyncio.run(dispatch(config(),'approved@synthetic.invalid','scheduling','A'*43,transport=f))
 assert result==status and len(f.messages)==(1 if error is None else 0)

def test_uncertain_commit_never_claims_delivery():
 class S:
  async def commit(self):raise RuntimeError('PRIVATE')
  async def rollback(self):pass
 a=N(status='sending');assert asyncio.run(finish_attempt(S(),a,config(),'approved@synthetic.invalid','scheduling','A'*43,transport=Fake()))=='uncertain'

def test_blank_credentials_are_not_ready():
 c=config();c.interview_smtp_password=SecretStr('');assert not ready(c)
