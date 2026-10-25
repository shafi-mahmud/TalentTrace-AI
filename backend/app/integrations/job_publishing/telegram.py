"""Opt-in fixed-channel Bot API transport. One send, no retries or paid broadcasts."""
import asyncio
import logging
import re
import httpx
from app.core.config import settings
from app.integrations.job_publishing.mcp_client import PublicationUnavailable, PublicationFailed
from app.schemas.job_publication import PublicationResult


class BotTokenRedactor(logging.Filter):
    def filter(self, record):
        record.msg = re.sub(r"bot[0-9]+:[A-Za-z0-9_-]+", "bot[REDACTED]", record.getMessage())
        record.args = ()
        return True

# HTTP client diagnostics otherwise include the Bot API credential-bearing URL.
for name in ("httpx", "httpcore.connection", "httpcore.http11", "httpcore.http2", "httpcore.proxy", "httpcore.socks"):
    logging.getLogger(name).addFilter(BotTokenRedactor())


class PublicationContentError(ValueError):
    pass


def publication_text(request):
    if not request._job_reference:
        raise PublicationContentError("Select an authorized saved job.")
    lines = [request.title, "Job Reference: " + request._job_reference]
    for label, value in (("Location",request.location),("Employment",request.employment_type),("Work arrangement",request.work_arrangement)):
        if value:lines.append(label + ": " + value.replace("_", " "))
    lines.append(request.summary)
    for label, items in (("Responsibilities",request.responsibilities),("Required skills",request.required_skills),
                         ("Preferred skills",request.preferred_skills),("Qualifications",request.qualifications)):
        if items:lines.append(label + "\n" + "\n".join("• " + item for item in items))
    text = "\n\n".join(lines)
    # Conservative UTF-16 count. Never silently truncate or split one request into posts.
    if len(text.encode("utf-16-le")) // 2 > 4096:
        raise PublicationContentError("Job content exceeds Telegram limits. Shorten the saved draft first.")
    return text


class TelegramJobPublisher:
    def __init__(self, configuration=None, *, transport=None):
        self.configuration = configuration or settings
        self.transport = transport

    async def publish(self, request):
        config = self.configuration
        token = config.telegram_bot_token.get_secret_value() if config.telegram_bot_token else ""
        channel = config.telegram_channel_id.get_secret_value() if config.telegram_channel_id else ""
        if (not config.telegram_publishing_enabled or not re.fullmatch(r"[0-9]{6,12}:[A-Za-z0-9_-]{20,128}",token)
                or not re.fullmatch(r"-100[0-9]{5,15}",channel)):
            raise PublicationUnavailable("Telegram publishing is unavailable.")
        text = publication_text(request)
        try:
            async with asyncio.timeout(20), httpx.AsyncClient(timeout=httpx.Timeout(15,connect=5),trust_env=False,follow_redirects=False,transport=self.transport) as client:
                response = await client.post("https://api.telegram.org/bot" + token + "/sendMessage",
                    json={"chat_id":channel,"text":text,"link_preview_options":{"is_disabled":True},"allow_paid_broadcast":False})
                if response.status_code != 200:raise ValueError()
                if len(response.content)>65536:raise ValueError()
                body = response.json()
                message = body.get("result",{})
                chat = message.get("chat",{})
                if (body.get("ok") is not True or type(message.get("message_id")) is not int or message["message_id"]<=0
                        or type(chat.get("id")) is not int or str(chat["id"])!=channel or chat.get("type")!="channel"
                        or message.get("text")!=text):
                    raise ValueError()
                return PublicationResult(destination="telegram",status="published",external_id=str(message["message_id"]))
        except Exception:
            # A timeout/error may follow delivery. Never echo the URL, key, response or job text.
            raise PublicationFailed("Telegram publication unconfirmed. Check the channel before another attempt.") from None


def get_telegram_publisher():
    return TelegramJobPublisher()
