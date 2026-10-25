# JD Assistant publishing — bounded trainer increment

Branch: `feature/multiplatform-job-publishing`, based on develop `cba35ab`.
No merge of the separate UI, analytics, F3/F4 or LinkedIn feature branches.

## Capabilities

| Destination | Implemented capability | Confirmation |
| --- | --- | --- |
| Discord | Existing authenticated FastAPI → official MCP stdio client → existing Discord webhook adapter. Requires separately configured local MCP environment and authorized webhook. | Only a validated provider message ID produces published status. Missing configuration/failure stays unavailable or unconfirmed. |
| Telegram | Opt-in server-configured channel through the official Bot API; one plain-text message with original Job Reference. | HTTP 200, ok=true, positive message ID, exact configured channel and matching text are required. Disabled by default. |
| LinkedIn | Full reviewed job content can be copied for recruiter-completed manual posting. | Manual action required; copied is explicitly not posted. No LinkedIn authentication, API posting, Jobs listing or browser automation. |
| Other platform | Same copyable full content for manual use elsewhere. | No automatic integration or delivery claim. |

The separate `feature/mcp-linkedin-publishing` tip `ccb19e5` was inspected: its
LinkedIn adapter only prepares manual text. It does not supply an automatic API.
This increment reuses the deployed Discord stack and the same manual-preview/copy
approach without merging unrelated code or requiring MCP for manual preparation.

## Recruiter workflow

Open a saved generated JD through the existing selected-job/conversation flow.
Type `publish`, `/publish`, `publish this job`, or `publish to Discord and LinkedIn`
in the composer, or choose **Review publishing** on the latest draft. The narrow
local command opens review; it never sends a publishing instruction to Groq.
Destinations start unchecked even if named in chat: review requires explicit selection.

Preview contains title, original Job Reference, full summary/requirements and
available employment/location context. Choose destinations, check the review
checkbox and confirm. Confirmation sends each selected automatic destination sequentially at most once
from that active UI attempt. Manual destinations expose copy controls; copying is not publication.
Results remain separate per destination, including partial success. Reopening review
retains in-memory receipts and disables already attempted destinations. No external calls occur on preview/open.
Only the latest saved draft with returned identity is eligible. Jobs without a
generated draft and restored/expired conversations that cannot supply it remain
blocked by the existing saved-conversation workflow; no content is invented.

Discord's existing server-owned application URL may be added by its existing
adapter; it cannot be supplied through the recruiter publication payload. Manual
copy contains only displayed job content/context, not undisclosed server config.

## Authorization, duplicates and failure boundaries

The existing endpoint rechecks authenticated recruiter/job ownership and compares
the complete submitted core draft to current saved content before any send **or
cached receipt**. Job Reference remains server-owned. Existing CSRF and bounded
text validation remain. Candidate data, arbitrary commands and provider credentials
are not publication inputs.

A bounded process-local map (maximum 1,000 attempts) keys owner plus normalized
request hash, including destination. Concurrent requests return conflict. Confirmed repeats reuse the
validated receipt without reposting; unconfirmed attempts remain blocked. Known
pre-transport unavailability releases the slot. There are no automatic retries.
A lost response may still mean delivery occurred: inspect the destination before
any separately considered new attempt. There is no delete/repost or retry button.

This is **not durable/global idempotency**: restart, multiple backend processes,
standalone MCP callers or revised content can permit another send. No new table,
migration, durable approval record, cross-process lock or publication history was
introduced. Do not restart as a retry mechanism. External provider confirmation
and database content comparison cannot be one atomic transaction. Future durable
publication governance needs separate scope; no exactly-once delivery claim.
The UI review checkbox is an explicit user action, not a persisted legal approval.

## Verification

- Focused backend publication and recruiter-record regressions: **54 passed**.
  Includes ownership/stale-content denial, no client Job Reference/form override,
  sanitized provider failures, concurrent/unconfirmed duplicate fencing, cached
  receipt reauthorization and the real in-process MCP protocol with mocked Discord.
- Full frontend: **307 passed**, zero failed/skipped. New cases cover bounded
  command recognition, saved-job-only chat review without inference, unchecked
  preview, complete manual text/reference and explicit destination confirmation.
- TypeScript app/node and Vite production build passed. Existing >500kB
  LiveInterviewPage chunk warning remains. Git whitespace checks passed.
- Initial protocol tests assumed a machine-local MCP venv. Their in-process fake
  transport now creates only temporary path-preflight files; the production
  executable checks are unchanged. Frontend harnesses explicitly supply the new
  component module. Those test-environment failures were resolved before final runs.

Providers were mocked; no actual posting, LinkedIn action, upload, clipboard use,
email, inference, Docker operation or database migration occurred. No new browser
visual/end-to-end acceptance is claimed. Actual Discord configuration/readiness
and any real synthetic publication require separate explicit owner approval.


## Telegram extension — 26 October 2026

Implemented on `feature/trainer-gap-closure-1` after CV selection commit `5127f7f`.
Existing Discord MCP and manual LinkedIn paths remain intact. Telegram does not
require another agent/MCP server, dependency, database or migration.

Private server configuration only:

- `TELEGRAM_PUBLISHING_ENABLED` defaults `false`.
- `TELEGRAM_BOT_TOKEN` is a private bot credential.
- `TELEGRAM_CHANNEL_ID` is the numeric channel identifier beginning `-100`.

The operator must provision an authorized bot with posting permissions in the
intended channel. Credentials/channel IDs cannot be supplied by browser requests.
No runtime settings were changed here. There is no channel discovery, account
linking, status probe or publication on startup. Missing/invalid configuration
returns unavailable without network access. UI labels automatic Telegram as requiring
configuration; selection never enables the server feature.

The adapter uses fixed `https://api.telegram.org`, redirects/proxies disabled,
15-second HTTP timeouts (5-second connect), a 20-second overall deadline, no retries,
and a conservative 4096 UTF-16-unit content limit. It sends the complete reviewed
job with original server-owned reference and context; it never silently truncates
or splits it. Oversized jobs fail before sending. No parse mode, attachments,
paid posts or paid broadcasts are used; link previews are disabled and
`allow_paid_broadcast` is explicitly false. Destination-specific API receipts are
validated before publication is reported. Raw provider errors and credential-bearing
URLs are not returned; HTTP diagnostic bot tokens are redacted.

Contract reference: [official Telegram sendMessage](https://core.telegram.org/bots/api#sendmessage)
(text limit, sent Message result, chat identifier and optional paid broadcasting).
Documentation was consulted; no Bot API request was executed.

Each explicitly selected destination is an independent attempt. A timeout or
unexpected/negative response is unconfirmed, never success; another selected
provider is not a fallback or retry. The existing process-local duplicate fence
blocks repeated uncertain attempts and revalidates ownership even for cached receipts.
It does not survive restart or coordinate multiple backend workers. Channel/bot
changes require operator review; there is no durable per-destination publication ledger.
Telegram currently includes displayed job content, not Discord's private configured
application-form link. Applicants can use the preserved Job Reference; form/link
configuration and real provider acceptance require separate review.

Verification uses HTTPX MockTransport and synthetic data only: exact channel/text
receipts, disabled/missing configuration, content bounds, malformed replies, errors,
timeouts, redirect refusal, token redaction, no retry, separate receipts, ownership,
stale preview, duplicate fencing and partial success. React handler tests verify
sequential selection, independent results and retained receipts without reposting.
No real external post, browser trial, paid call or service activation occurred.

Final verification: **231 combined backend passed, 1 skipped** (explicit disposable
PostgreSQL gate unavailable). A subsequent **17 Telegram-focused tests passed**,
including the newly added real authentication/ownership/stale-preview/reference
case. These runs overlap; they are not additive totals. **331 full frontend tests
passed**, TypeScript and Vite production build passed, and diff checks passed.
The initial migration-chain test was invoked from the repository root and could not
find backend/alembic.ini; rerunning from backend passed without schema changes.
The existing >500 kB interview bundle warning remains. Real channel authorization,
delivery and browser acceptance remain unverified.
