# JD chat and private publishing — 28 October 2026

## Implemented / tested

The JD workspace is centered with an 850px maximum width. Its history is independently scrollable at 65vh/dvh; the composer follows at the bottom with a compact bottom-right provider selector. History can receive keyboard focus; acknowledgement moves focus to its disclosure and Cancel returns to the composer. Narrow layouts wrap the toolbar.

Available Groq defaulting and conversation provider pinning are unchanged. The JD composer no longer repeats the checkbox: the first external submission opens an explicit **Allow Groq and send** acknowledgement covering JD conversation/policy context. Nothing is sent before that action. Approval remains in component memory for the open conversation only; New chat, restore/remount and provider changes require acknowledgement again. Every external request still carries the backend-required explicit flag. CV consent remains a separate unchecked control and cannot be hidden by the compact JD option. Publishing review/unchecked destinations/confirmation and duplicate safeguards remain unchanged.

50 focused frontend tests passed, zero failed/skipped, covering acknowledgement gating/cancellation/reuse/reset, separate CV consent, saved conversation/refinement and publishing. TypeScript and production build passed (existing large-chunk advisory). No new visual/browser acceptance or real Groq inference is claimed. **UI deployment remains pending owner approval**; existing Groq containers/images/database were not replaced or restarted.

## Actual private Discord demonstration

Only saved fictional job **TT-JOB-49C51587C3524024, revision 2** was used. Authenticated API reads verified its identity/revision and restored generated draft before preparing a private preview. Owner explicitly reviewed/approved the private Discord destination and authorized one post. The normal authenticated publish endpoint revalidated saved content and used the existing **Discord MCP webhook adapter**. Exactly one POST to the application publishing endpoint was issued; no retry. A published provider receipt was returned. Read-only webhook message retrieval verified that receipt exists, its channel matches the reviewed destination, and its embedded Job Reference matches the authorized job.

Webhook metadata was readable before sending. Dedicated MCP venv dependency, actual stdio tool discovery and mocked protocol-delivery checks passed. An initial check used backend Python and failed its separate pinned-version assertion; rerunning with the intended MCP venv passed, without changing either environment. No application defect was inferred from that invocation error.

Private preview, destination metadata, single-use send intent, receipt and verification are preserved under ignored `data/jd-chat-publishing-20261028/`. Do not repeat that send or use a restart as a duplicate-send workaround. Existing publication idempotency is process-local, not durable exactly-once delivery. No private destination IDs, credentials or webhook URLs are copied here.

## Telegram: BLOCKED, zero attempts

The existing **Telegram Bot API adapter**, not MCP, is implemented. Token and channel ID are absent from both runtime and original private configuration. No Telegram lookup/send occurred and no new Telegram server was built.

Owner-only setup: enter TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID directly into the existing ignored private runtime environment; never paste them in chat. Select an owner-approved private test channel and give the bot posting permission. TELEGRAM_PUBLISHING_ENABLED must remain off until that exact destination is reviewed. Note that compose.groq.yaml currently explicitly forces this flag false: enabling it needs a reviewed ignored runtime Compose override, plus separately approved backend recreation; simply adding the env-file key will not override that safeguard. No runtime configuration or deployment was changed in this task. Verify permissions without posting, prepare/review the exact saved draft and obtain explicit destination authorization before one future send. Never auto-retry uncertain delivery.


## Configuration follow-up — 28 October 2026

The reviewed Compose fix removes the unconditional Telegram false override.
An explicit value in the private runtime env_file is now honored; application
Settings still defaults to false when absent, and credentials/owner-approved
destination remain required. Four focused configuration tests pass, including
private opt-in and safe default isolation. This change does not recreate services
or send a Telegram message; the earlier blocked live-readiness result is historical.
