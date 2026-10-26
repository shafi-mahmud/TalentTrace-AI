"""Offline image acceptance. Always synthetic + mocked; never a real publication."""
import asyncio
import importlib.metadata
import json
import os
from pathlib import Path
import sys

import httpx
from mcp import Client
from mcp.client.stdio import StdioServerParameters, stdio_client

ROOT = Path('/app/job-publishing-mcp')
sys.path.insert(0, str(ROOT))
from talenttrace_job_publishing import server
from talenttrace_job_publishing.config import Settings
from talenttrace_job_publishing.publishers.discord import DiscordPublisher


async def check():
    # The backend's environment is unchanged; only this child venv has MCP pins.
    for package, version in [('mcp','2.3.0'), ('pydantic','2.13.5'),
                             ('pydantic-settings','2.15.0'), ('httpx','0.28.1')]:
        assert importlib.metadata.version(package) == version
    params = StdioServerParameters(
        command=str(ROOT / '.venv/bin/python'),
        args=['-B','-m','talenttrace_job_publishing.server'], cwd=str(ROOT),
        env={'DISCORD_WEBHOOK_URL':'intentionally_invalid_discovery_only'},
    )
    with open(os.devnull, 'w') as diagnostics:
        async with asyncio.timeout(20):
            async with Client(stdio_client(params, errlog=diagnostics), read_timeout_seconds=15) as client:
                tools = (await client.list_tools()).tools
                assert [tool.name for tool in tools] == ['publish_job']
                # Never call a business tool across this unmodified subprocess.

    calls = []
    reference = 'TT-JOB-0000000000000001'
    def handler(request):
        payload = json.loads(request.content)
        assert payload['allowed_mentions']['parse'] == []
        assert any(field['name']=='Job Reference' and field['value']==reference
                   for field in payload['embeds'][0]['fields'])
        calls.append(True)
        return httpx.Response(200, json={'id':'123456789012345679'})

    config = Settings(_env_file=None, discord_webhook_url=
        'https://discord.com/api/webhooks/123456789012345678/' + 'synthetic_token_' * 4)
    original_config, original_publisher = server.load_settings, server.DiscordPublisher
    try:
        server.load_settings = lambda: config
        server.DiscordPublisher = lambda settings: DiscordPublisher(settings, transport=httpx.MockTransport(handler))
        async with Client(server.mcp) as client:
            result = await client.call_tool('publish_job', {'job':{
                'job_reference':reference, 'title':'Fictional Docker readiness role',
                'summary':'Synthetic local protocol verification only.',
                'responsibilities':['Build APIs'], 'required_skills':['Python'],
                'qualifications':['Demonstrated API development'],
            }})
        assert not result.is_error and result.structured_content['status']=='published'
        assert len(calls) == 1
    finally:
        server.load_settings, server.DiscordPublisher = original_config, original_publisher
    return {'pinned_dependencies':True,'real_stdio_tool_discovery':True,
            'mock_protocol_delivery':True,'mock_transport_calls':len(calls),'live_post':False}


if __name__ == '__main__':
    try:
        print(json.dumps(asyncio.run(check())))
    except Exception as error:
        print(json.dumps({'check_failed':True,'category':type(error).__name__,'live_post':False}))
        raise SystemExit(1)
