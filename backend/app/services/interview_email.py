"""No retries/body logging. SMTP acceptance is not proof of mailbox delivery."""
import asyncio,re,smtplib,socket,ssl
from email.message import EmailMessage
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from datetime import timedelta
from fastapi import HTTPException
ADDRESS=re.compile(r'^[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$')
def recipient(configuration,value):
 if not isinstance(value,str) or len(value)>254 or not ADDRESS.fullmatch(value) or value.casefold() not in {s.casefold() for s in configuration.interview_email_recipients}:
  raise HTTPException(422,'Use an explicitly approved synthetic recipient.')
 if value.rsplit('@',1)[1].lower() in {'example.com','example.org','example.net','example.test'}:raise HTTPException(422,'Fictional recipient domains cannot receive email.')
 return value.casefold()
def ready(c):
 origin=urlsplit(c.interview_public_origin or '')
 return c.interview_email_enabled and c.environment=='development' and c.livekit_synthetic_demo_enabled and bool(c.interview_email_sender and ADDRESS.fullmatch(c.interview_email_sender)) and origin.scheme=='https' and bool(origin.hostname) and not origin.username and not origin.password and origin.path in ('','/') and not origin.query and not origin.fragment and bool(c.interview_smtp_host and c.interview_smtp_username and c.interview_smtp_password and c.interview_smtp_username.get_secret_value() and c.interview_smtp_password.get_secret_value())
def template(c,kind,token,interview=None):
 if not re.fullmatch(r'[A-Za-z0-9_-]{43}',token):raise ValueError('Invalid capability')
 origin=c.interview_public_origin.rstrip('/')
 if kind=='scheduling':return 'Choose your synthetic interview slot',f'You have been selected for a synthetic demonstration interview. Choose an available 60-minute Asia/Dhaka slot using your private scheduling link:\n{origin}/interview-schedule#schedule={token}\nDo not forward this link. It expires in seven days.'
 if kind!='confirmation' or interview is None:raise ValueError('Invalid email kind')
 start=interview.scheduled_at.astimezone(ZoneInfo('Asia/Dhaka'));end=start+timedelta(minutes=interview.duration_minutes)
 return 'Synthetic interview booking confirmation',f'Interview date: {start:%d %B %Y}\nTime: {start:%H:%M}–{end:%H:%M} Asia/Dhaka\nDuration: {interview.duration_minutes} minutes\nPrivate joining link: {origin}/interview-join#invite={token}\nJoin from ten minutes before the interview. No recording or persisted transcript.'
class SMTPTransport:
 def send(self,c,to,subject,body):
  message=EmailMessage();message['From']=c.interview_email_sender;message['To']=to;message['Subject']=subject;message.set_content(body)
  with smtplib.SMTP_SSL(c.interview_smtp_host,c.interview_smtp_port,timeout=10,context=ssl.create_default_context()) as server:
   server.login(c.interview_smtp_username.get_secret_value(),c.interview_smtp_password.get_secret_value())
   if server.send_message(message):raise smtplib.SMTPRecipientsRefused({})
async def dispatch(c,to,kind,token,interview=None,transport=None):
 if not ready(c):return 'not_configured'
 try:
  to=recipient(c,to);subject,body=template(c,kind,token,interview)
  await asyncio.to_thread((transport or SMTPTransport()).send,c,to,subject,body)
  return 'accepted'
 except (smtplib.SMTPRecipientsRefused,smtplib.SMTPAuthenticationError):return 'failed'
 except (TimeoutError,socket.timeout,OSError,smtplib.SMTPServerDisconnected):return 'uncertain'
 except Exception:return 'uncertain'
async def finish_attempt(session,attempt,c,to,kind,token,interview=None,transport=None):
 status=await dispatch(c,to,kind,token,interview,transport)
 attempt.status=status
 try:await session.commit()
 except Exception:
  await session.rollback();return 'uncertain'
 return status
