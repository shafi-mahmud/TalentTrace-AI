# JD Assistant publishing — bounded trainer increment

Branch: `feature/multiplatform-job-publishing`, based on develop `cba35ab`.
No merge of the separate UI, analytics, F3/F4 or LinkedIn feature branches.

## Capabilities

| Destination | Implemented capability | Confirmation |
| --- | --- | --- |
| Discord | Existing authenticated FastAPI → official MCP stdio client → existing Discord webhook adapter. Requires separately configured local MCP environment and authorized webhook. | Only a validated provider message ID produces published status. Missing configuration/failure stays unavailable or unconfirmed. |
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
checkbox and confirm. Confirmation sends Discord at most once from that active
UI attempt. Manual destinations expose copy controls; copying is not publication.
Results remain separate per destination. No external calls occur on preview/open.
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
request hash. Concurrent requests return conflict. Confirmed repeats reuse the
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
