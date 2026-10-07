"""Official MCP stdio client; the existing standalone server owns Discord."""
import asyncio
import os
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client
from app.core.config import REPOSITORY_ROOT, Settings, settings
from app.schemas.job_publication import PublicationResult, RecruiterPublishRequest


class PublicationUnavailable(RuntimeError):
    pass


class PublicationFailed(RuntimeError):
    pass


class MCPJobPublisher:
    def __init__(self, configuration: Settings | None = None):
        self._configuration = configuration or settings

    async def publish(self, request: RecruiterPublishRequest) -> PublicationResult:
        directory = REPOSITORY_ROOT / "job-publishing-mcp"
        executable = directory / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        if not executable.is_file() or not (directory / "talenttrace_job_publishing/server.py").is_file():
            raise PublicationUnavailable("The local MCP publishing server is unavailable.")
        job = request.mcp_job()
        if self._configuration.application_form_url is not None:
            job["application_url"] = self._configuration.application_form_url.get_secret_value()
        params = StdioServerParameters(command=str(executable),
            args=["-B", "-m", "talenttrace_job_publishing.server"], cwd=str(directory),
            env={"DISCORD_WEBHOOK_URL": os.environ["DISCORD_WEBHOOK_URL"]} if "DISCORD_WEBHOOK_URL" in os.environ else None)
        try:
            # Fixed executable/tool; no client-selected commands or credentials.
            # No subprocess diagnostics, raw tool errors or automatic retries.
            with open(os.devnull, "w", encoding="utf-8") as diagnostics:
                async with asyncio.timeout(35):
                    async with Client(stdio_client(params, errlog=diagnostics), read_timeout_seconds=30) as client:
                        result = await client.call_tool("publish_job", {"job": job})
                        if result.is_error:
                            raise PublicationFailed("Publication was not confirmed.")
                        return PublicationResult.model_validate(result.structured_content)
        except Exception:
            raise PublicationFailed("Publication was not confirmed. Check delivery before another attempt.") from None


def get_job_publisher() -> MCPJobPublisher:
    return MCPJobPublisher()
