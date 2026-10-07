# TalentTrace Job Publishing MCP

**Status: Implemented — standalone foundation; real Discord smoke verification pending.**

TalentTrace owns this small MCP server. Its one business tool, `publish_job`,
accepts a validated `JobCircular`, delegates to `DiscordPublisher`, and returns
only `destination`, `status`, and the external Discord message ID. It uses the
official Python MCP SDK v2 (`MCPServer`), with stdio as the default transport.
It has no FastAPI or LangGraph dependency.

## Implemented

- Strict, bounded plain-text job fields: title, summary, responsibilities,
  required/preferred skills, qualifications, and optional location/employment/
  work arrangement. Unknown fields, HTML/angle-bracket markup, unsafe controls,
  blanks and invalid types are rejected. Whitespace is normalized.
- Server-side configuration: environment overrides the ignored repository-root
  `.env`. Configuration is loaded when publishing, not on import. The webhook
  is a protected `SecretStr`; configuration errors never echo its value.
- Only HTTPS `discord.com` or legacy `discordapp.com` webhook paths are allowed:
  `/api/webhooks/<id>/<token>` or `/api/v10/webhooks/<id>/<token>`. Credentials,
  alternate URLs, ports, userinfo, query strings and fragments cannot be chosen
  through the tool. `wait=true` is added by the adapter itself.
- Async Discord publishing: one embed, disabled mentions, explicit timeouts,
  no redirects, no environment proxies and no automatic retries. Provider
  response bodies and headers are never returned. Credential-bearing HTTP
  library logs are disabled.
- Payload checks before HTTP: title 256, description 4096, field value 1024,
  at most 25 fields and total embed text 6000, counted conservatively in UTF-16
  units. Long sections or oversized totals fail safely; content is not truncated
  or split across multiple messages. See [Discord webhook documentation](https://docs.discord.com/developers/resources/webhook)
  and [embed limits](https://docs.discord.com/developers/resources/message#embed-limits).
- Fixed MCP input errors prevent submitted content or undeclared credentials
  being echoed by SDK argument validation. Tool annotations identify publication
  as an external, non-idempotent write.
- Mocked tests include MCP protocol tool discovery and structured output.
  Tests never read the real `.env` or send real Discord messages; external
  network connections and the real HTTP transport are blocked.

## Local setup and tests

From `job-publishing-mcp/`, use a separate ignored virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m pytest -q
```

On Linux, use `.venv/bin/python` for these commands. Runtime dependencies are
pinned in `requirements.txt`; pytest is separate in `requirements-dev.txt`.
See the [official SDK v2 release](https://github.com/modelcontextprotocol/python-sdk/releases/tag/v2.3.0)
and [client documentation](https://py.sdk.modelcontextprotocol.io/client/).

Set `DISCORD_WEBHOOK_URL` only in the ignored root `.env` or server environment.
The tracked root `.env.example` contains a non-working placeholder only.
Never paste the real webhook into a command, job field, README or test.

Run the server from this directory:

```powershell
.\.venv\Scripts\python.exe -m talenttrace_job_publishing.server
```

It waits for an MCP client on stdin/stdout; it does not open an HTTP port or
publish on startup. Stdout is reserved for the protocol.

## Manual synthetic smoke publication — not yet verified

After reviewing this increment, run **once** from `job-publishing-mcp/`:

```powershell
.\.venv\Scripts\python.exe -m talenttrace_job_publishing.smoke_client --publish-synthetic
```

This launches the actual server with the current Python executable, connects
over stdio using the official MCP client and calls `publish_job` with a fixed
synthetic TalentTrace job clearly marked as not a real vacancy. The server
reads its configured webhook; the client prints only validated result metadata
or a generic failure. Subprocess diagnostics are not forwarded. Without
`--publish-synthetic`, nothing is sent.

Timeouts or lost responses can occur after Discord accepted a message. Check
the channel before retrying; there is no deduplication or automatic retry.
This increment supports ordinary text channels, not forum/media thread setup.

## Planned — not implemented

- Real MCP-to-Discord smoke verification, until manually performed.
- TalentTrace backend MCP client integration and recruiter chatbot.
- JD approval enforcement, authorization and publication audit/persistence.
- Blogger, Telegram and other destinations, including LinkedIn/X.

An MCP server exposes protocol tools; it is not a LangGraph agent and does not
generate or approve a JD. A future backend MCP client will map an approved JD
into `JobCircular` and call this same tool. The fields are designed for that
mapping; no backend contract or workflow is changed in this increment.

Until approval enforcement is added, use only synthetic demo circulars from
trusted local clients. Automated tests mock Discord so repeatable tests cannot
publish accidentally or require credentials.
