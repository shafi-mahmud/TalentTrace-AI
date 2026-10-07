"""One bounded webhook publication, with no retries or credential-bearing logs."""

import logging
from typing import Any

import httpx
from pydantic import ValidationError

from ..config import Settings
from ..schemas import JobCircular, PublishJobResult


class PublicationError(RuntimeError):
    """Controlled publication failure; does not echo content or HTTP details."""


def discord_length(text: str) -> int:
    # Conservative UTF-16 units also keep non-BMP characters within Discord limits.
    return len(text.encode("utf-16-le")) // 2


def format_payload(job: JobCircular) -> dict[str, Any]:
    fields = []
    for name, items in (
        ("Responsibilities", job.responsibilities),
        ("Required skills", job.required_skills),
        ("Preferred skills", job.preferred_skills),
        ("Qualifications", job.qualifications),
    ):
        if items:
            fields.append({
                "name": name,
                "value": "\n".join(f"• {item}" for item in items),
                "inline": False,
            })
    for name, value in (
        ("Location", job.location),
        ("Employment type", job.employment_type),
        ("Work arrangement", job.work_arrangement),
    ):
        if value:
            fields.append({"name": name, "value": value.replace("_", " "), "inline": True})

    footer = "TalentTrace AI • Job circular"
    total = discord_length(job.title) + discord_length(job.summary) + discord_length(footer)
    total += sum(
        discord_length(field["name"]) + discord_length(field["value"])
        for field in fields
    )
    if (
        discord_length(job.title) > 256
        or discord_length(job.summary) > 4096
        or len(fields) > 25
        or any(discord_length(field["value"]) > 1024 for field in fields)
        or total > 6000
    ):
        raise PublicationError(
            "Job circular exceeds Discord publication limits. Shorten the content."
        )
    return {
        "allowed_mentions": {"parse": [], "users": [], "roles": [], "replied_user": False},
        "embeds": [{
            "title": job.title, "description": job.summary,
            "fields": fields, "footer": {"text": footer},
        }],
    }


class DiscordPublisher:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self._webhook = settings.require_webhook()
        self._transport = transport

    async def publish(self, job: JobCircular) -> PublishJobResult:
        payload = format_payload(job)
        # HTTPX's INFO request log contains the credential-bearing URL. Never emit it.
        logging.getLogger("httpx").disabled = True
        for name in (
            "httpcore.connection", "httpcore.http11", "httpcore.http2",
            "httpcore.proxy", "httpcore.socks",
        ):
            logging.getLogger(name).disabled = True
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=False,
                trust_env=False,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    self._webhook.get_secret_value(), params={"wait": "true"}, json=payload
                )
            if response.status_code != 200:
                raise PublicationError(
                    "Discord did not confirm publication. No automatic retry was attempted."
                )
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError
            return PublishJobResult(external_id=data.get("id"))
        except PublicationError:
            raise
        except httpx.TimeoutException:
            raise PublicationError(
                "Discord publication timed out. Delivery may have occurred; "
                "check the channel before retrying."
            ) from None
        except (httpx.RequestError, ValueError, ValidationError):
            raise PublicationError(
                "Discord publication could not be confirmed. Check the channel before retrying."
            ) from None
        except Exception:
            raise PublicationError(
                "Discord publication failed. Check the channel before retrying."
            ) from None
