"""Manual synthetic MCP-to-Discord proof. Never imported as an automatic test."""

import argparse
import asyncio
import os
from pathlib import Path
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

from .schemas import JobCircular, PublishJobResult


def synthetic_job() -> JobCircular:
    return JobCircular(
        title="TalentTrace Demo — Backend AI Engineer (Synthetic)",
        summary="Synthetic evaluation circular: build secure AI-enabled backend services. This is not a real vacancy.",
        responsibilities=["Develop FastAPI services", "Write automated tests", "Follow secure engineering practices"],
        required_skills=["Python", "FastAPI", "PostgreSQL", "Git"],
        preferred_skills=["Retrieval workflows"],
        qualifications=["Demonstrable backend development skills"],
        work_arrangement="remote",
    )


async def publish_synthetic() -> PublishJobResult:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "talenttrace_job_publishing.server"],
        cwd=str(Path(__file__).resolve().parents[1]),
        # Pass only this explicit override; the server itself reads the root .env.
        env={"DISCORD_WEBHOOK_URL": os.environ["DISCORD_WEBHOOK_URL"]}
        if "DISCORD_WEBHOOK_URL" in os.environ else None,
    )
    # Do not forward subprocess diagnostics or raw provider failures to the console.
    with open(os.devnull, "w", encoding="utf-8") as diagnostics:
        async with Client(stdio_client(params, errlog=diagnostics), read_timeout_seconds=30) as client:
            result = await client.call_tool("publish_job", {"job": synthetic_job().model_dump(mode="json")})
            if result.is_error:
                raise RuntimeError("Publication was not confirmed.")
            return PublishJobResult.model_validate(result.structured_content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Manually publish one synthetic demo job THROUGH MCP.")
    parser.add_argument("--publish-synthetic", action="store_true", help="Sends one real Discord message; run only after review.")
    args = parser.parse_args()
    if not args.publish_synthetic:
        print("No publication sent. Use --publish-synthetic only after review.")
        return 0
    try:
        result = asyncio.run(publish_synthetic())
    except Exception:
        print("MCP smoke publication could not be confirmed. Check configuration and the channel before retrying.")
        return 1
    print(result.model_dump_json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
