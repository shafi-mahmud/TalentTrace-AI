# LinkedIn job promotion

## Implemented

JD Assistant now offers **Prepare for LinkedIn** alongside the existing Discord
publication action. LinkedIn is a manual feed-announcement destination. It is
**not automated LinkedIn publishing** and does not create a LinkedIn Jobs listing.

Execution: reviewed saved draft → authenticated
`POST /api/v1/recruiter-chat/linkedin/prepare` → existing ownership/content checks
→ official MCP stdio client → existing MCP server's read-only
`prepare_linkedin_job` tool → `LinkedInPublisher.prepare()`.
Discord continues using `publish_job` and its existing response contract.

The preparation result has `destination=linkedin`, `status=prepared`,
`mode=manual`, and bounded announcement text. It never has a publication ID.
The server supplies the saved job reference and optional trusted
`APPLICATION_FORM_URL`; clients cannot supply either. Title, location,
employment type, requirements and qualifications come from the existing bounded
job contract. Long sections are shortened with a visible notice. An announcement
exceeding 3,000 characters fails safely; review/shorten the draft or application URL.
Preparation does not load LinkedIn credentials, contact LinkedIn, or write records.

Recruiter steps:

1. Open a saved/generated owned draft in JD Assistant and review it.
2. Click **Prepare for LinkedIn** and review the preview, including shortened text.
3. Click **Copy reviewed announcement** and confirm. Cancellation copies nothing.
4. Open LinkedIn with the provided ordinary feed link, create a post, paste,
   check the account/audience and announcement, then explicitly click Post there.

Opening LinkedIn carries no job text or credentials in its URL. The app always
says **Prepared for LinkedIn sharing — not published**. It cannot verify manual
delivery. It suppresses duplicate in-flight preparation, disables preparation
after success for that displayed draft, and never retries automatically.
Repeated preparation is side-effect free. **These are not durable cross-browser
publication safeguards**: the recruiter must check their feed before reposting.
Existing Discord duplicate prevention remains unchanged (per displayed draft;
no new durable publication ledger).

## Authorization and configuration

No LinkedIn environment variables or OAuth setup are required for this manual
mode. No local LinkedIn configuration was found in the inspected F4 root env
files or current process environment. Developer-portal app/product access has
not been independently verified; this must not be mistaken for approved access.
The separate worktree deliberately does not copy private F4 configuration.
Its MCP runtime needs the existing project MCP virtual environment, as for Discord.

## Recommended future official API path — not implemented

LinkedIn's [Posts API](https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api)
creates ordinary feed posts. Member publication requires `w_member_social`;
organization publication has separate permissions and administrator-role rules.
An approved developer application/product and member consent must be verified
before enabling an API adapter. The
[access guide](https://learn.microsoft.com/en-us/linkedin/shared/authentication/getting-access)
describes the Share on LinkedIn product; the
[authorization-code guide](https://learn.microsoft.com/en-us/linkedin/shared/authentication/authorization-code-flow)
describes client credentials, exact HTTPS callback, state validation and member
consent. A future adapter must store secrets only in protected server-side local
configuration, never the browser, MCP arguments, Git or logs. Do not add tokens
until that adapter and its authorization flow exist.

Official Posts requests use `POST https://api.linkedin.com/rest/posts`, a supported
`LinkedIn-Version`, `X-Restli-Protocol-Version: 2.0.0` and a bearer token.
Successful creation returns HTTP 201 and `x-restli-id`. Before enabling writes,
add durable owner/job/destination publication attempts and reconciliation for
uncertain delivery, plus mocked 401/403/429/provider-failure tests. Do not
silently fall back to a different account, platform or automatic retry.
The typed preparation adapter/result provides a separate extension point without
changing Discord or mislabeling preparation as API success.

Formal [Job Posting API access](https://learn.microsoft.com/en-us/linkedin/talent/job-postings/api/overview)
is restricted to approved integrations; the current overview says new Job Posting
API partnerships are not being accepted and points applicants to Apply Connect.
An ordinary feed post must never be described as a Jobs listing.

## Verification and limits

Tests exercise the MCP protocol, offline formatter, backend authorization and
sanitized errors, frontend authenticated request/response validation, duplicate
click protection and copy cancellation with mocked browser APIs. Existing Discord
HTTP transports remain mocked and regression-tested. OAuth/provider error cases
only verify that manual mode ignores credentials and never claims publication;
they do **not** verify a LinkedIn API adapter, which is not implemented.
No LinkedIn/Discord publication or live OAuth interaction was performed. Manual
sharing and new UI behavior have not been live-verified in an authenticated browser.

Verified locally: 115 MCP tests, 57 backend publishing/ownership tests and 175
frontend tests passed; no skips in these suites. Both TypeScript configurations,
production Vite build, Python compilation and whitespace checks passed. Vite
reported a large LiveInterviewPage chunk warning; no interview changes were made.

For an authenticated browser test, use this separate worktree's backend and
frontend on unused loopback ports, with private configuration supplied locally.
Do not expect the original F4 server at 5184 to contain this branch's changes.
Set `VITE_API_BASE_URL` to the separate backend and allow that exact frontend
origin in its `CORS_ORIGINS`. Use existing synthetic login and a saved synthetic
draft; do not generate a new JD just for this test. Test preparation, cancellation
and copy only, then stop before LinkedIn's Post button. No migration or LinkedIn
credentials are needed. Do not restart the original F4 processes.
