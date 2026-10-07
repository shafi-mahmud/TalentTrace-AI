"""Standalone stdio MCP server; one publishing tool, no FastAPI or LangGraph."""

from mcp.server import MCPServer
from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

from .config import PublishingConfigurationError, load_settings
from .publishers.discord import DiscordPublisher, PublicationError
from .schemas import JobCircular, PublishJobResult


async def validate_publication_arguments(
    ctx: ServerRequestContext, call_next: CallNext
) -> HandlerResult:
    # The SDK's generated argument wrapper may echo invalid input. Validate first
    # and return a fixed error, including when an undeclared credential is supplied.
    if ctx.method == "tools/call" and (ctx.params or {}).get("name") == "publish_job":
        arguments = (ctx.params or {}).get("arguments")
        try:
            if not isinstance(arguments, dict) or set(arguments) != {"job"}:
                raise ValueError
            JobCircular.model_validate(arguments["job"])
        except (ValueError, ValidationError):
            return CallToolResult(
                is_error=True,
                content=[TextContent(type="text", text="Invalid job circular. Supply only the declared plain-text job fields.")],
            )
    return await call_next(ctx)


mcp = MCPServer("TalentTrace Job Publishing", middleware=[validate_publication_arguments])


@mcp.tool(annotations=ToolAnnotations(
    read_only_hint=False, destructive_hint=True,
    idempotent_hint=False, open_world_hint=True,
))
async def publish_job(job: JobCircular) -> PublishJobResult:
    """Publish a job circular to the server-configured Discord channel.

    This has an external side effect. Do not retry without checking delivery.
    Approval enforcement is not implemented; use synthetic demo content only.
    """
    try:
        publisher = DiscordPublisher(load_settings())
        return await publisher.publish(job)
    except (PublishingConfigurationError, PublicationError) as error:
        raise ToolError(str(error)) from None
    except Exception:
        raise ToolError("Job publication failed. Check delivery before retrying.") from None


if __name__ == "__main__":
    mcp.run()
