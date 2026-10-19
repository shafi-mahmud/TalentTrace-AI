# F11 Increment 5B: secure delivery, independent consent and UI

## Implemented scope

Based on hardened 5A `687797e`, branch `feature/f11-copilot-delivery`.
This increment adds authenticated delivery and a React panel around 5A. It does
**not** connect Whisper or caption events. It is not live F11 completion or an
innovation-success claim. Nothing is enabled in an existing runtime or database.

`INTERVIEW_COPILOT_ENABLED=false` is the default in Settings, the example env and
Docker Compose. Docker still needs no additional service, model or network.
Tests enable only their isolated in-memory app settings; no private .env changes.
There are no migrations, SQL writes, transcript endpoints, models or providers.

## Execution and authorization

| Route, under /api/v1 | Method | Boundary and effect |
| --- | --- | --- |
| /interview-copilot/config | GET | Public fixed disclosure and default-off status; no identity or requirements. |
| /jobs/{job}/interviews/{interview}/copilot | GET | Authenticated owner, fresh authorized scope; status and optional suggestion. |
| same recruiter path + /prepare | POST | Explicitly replace the assistant run; neither participant is opted in. |
| same recruiter path + /consent | POST | Recruiter accepts, declines or withdraws for run UUID/epoch/version. |
| same recruiter path + /dismiss | POST | Dismiss only an actually emitted current suggestion fingerprint. |
| /interview-access/copilot | GET | Existing candidate session; consent status only. |
| /interview-access/copilot/consent | POST | Independent candidate accept, decline or withdraw; no identity parameters. |

Every mutation uses existing X-TalentTrace-Request and origin verification.
Candidate cookies keep HttpOnly, SameSite=strict, existing Secure policy and the
unchanged `/api/v1/interview-access` path. No broader cookie or browser bearer is
introduced. Run UUIDs are freshness identifiers, not authorization capabilities.
API middleware applies Cache-Control: no-store, including suggestion responses.

The API reuses current_recruiter, owned_job, candidate_session and join_window.
Every retrieval checks job ownership, current confirmed snapshot/revision,
interview association and join window, active recruiter, invitation expiry and
revocation, the candidate-session hash and the pinned recruiter-session hash.
Candidate rotation, owner logout and criteria changes cannot silently retain a
previous run. The candidate never receives suggestions, coverage states or job
requirement content, even with a valid candidate cookie.

Job-parent then interview-child row locks serialize scope checking against
criteria/invitation changes and storage withdrawal. GETs perform SELECTs (including
locks) but never add, flush, commit or otherwise mutate persistent records. The
request session rolls back/closes after use. The final in-memory read/publication
is serialized under the run lock. No inference starts from a polling GET.

## Consent, lifecycle and race behavior

The exact approved disclosure appears separately from captions and storage:

> The interview assistant can temporarily process recognized speech from this interview to suggest job-related follow-up questions to the interviewer. Suggestions are not shown to the candidate. This feature does not automatically score or decide hiring outcomes. This version processes speech locally without sending it to an external AI provider, and does not retain an additional saved co-pilot transcript.

The UI also explicitly says live suggestions are **not connected in 5B**. The
disclosure describes the local processing contract; actual event processing in
this increment happens only in internal synthetic tests.

A recruiter prepares one run, bound to interview/job/owner, exact requirements,
criteria revision and both current participant authentication identities. Both
independently accept the same run UUID/epoch/version. Joining, caption consent and
storage consent never imply assistant consent. Decline/withdraw does not stop
media or captions. An interview with a durable storage-withdrawal marker cannot
prepare another assistant run in this conservative first version.

Each run lasts at most 120 seconds or the authorization deadline, whichever is
sooner; at most 32 runs exist in one process. Suggestions expire after at most
15 seconds, with the original 5A event bounds, cooldown and deduplication intact.
One in-flight synchronous processing slot per run rejects concurrent work.
A single optional lifespan janitor sweeps once per second; no per-run background
queues exist. Process shutdown clears the manager. Restart starts consent OFF.

Withdrawal increments an epoch fence and clears context, receipts and results
before returning. A delayed calculation can finish, but its old run/epoch cannot
publish. Run replacement uses a new UUID; old requests fail. Storage privacy
withdrawal invalidates the assistant **after its durable revoke commit and before
physical deletion**, including when deletion fails. Subsequent API checks also
read the durable marker. The assistant does not change storage authorization,
retention, deletion state or existing F4/F5 results.

Authentication/revision changes are checked at every API read/action; no cached
result authorizes access. An already-delivered HTTP response cannot be remotely
erased. UI polling observes other-browser withdrawal on its next successful poll
(normally two seconds); local withdrawal immediately hides the suggestion and
fences older responses. Failed requests clear display and never retry mutations.
Disconnect/navigation sends best-effort withdrawal and clears local state. A
closed browser is not proof of delivered withdrawal: server expiry is the backstop.
There is no server LiveKit-disconnect subscription in 5B. Direct F4 lifecycle
hooks, including authoritative room termination, remain 5C work.

This state is **process-local, not durable or multi-worker coordinated**. Use one
backend process only for this development increment. Load balancing, independent
workers and cross-process immediate revocation are unsupported. Python reference
release is not memory zeroization. Recognition/suggestion input and consent are
not stored in PostgreSQL or browser persistence. Only hashes of existing auth
identities, bounded requirement metadata, short-lived logic state and results
exist in memory. No text/credential logging is introduced.

## Internal synthetic acceptance seam

Only tests call Delivery.submit_synthetic. No router invokes it, and no public
route accepts speech or arbitrary event text. The supplied Update must match the
current server-generated binding and have original run-relative timestamps
strictly after the instant both consents became active. Earlier speech is refused;
it is never retimestamped/replayed. The future trusted adapter must preserve that
identity/time contract. The synthetic flag is not production authorization.

Example tested sequence: question event 1, “Explain Python lists”; answer event 2,
“Lists are mutable ordered sequences.” After independent consents and the settling
interval, the owner receives the provisional Python example prompt with an
internal-source-sequence reason. The candidate receives only consent status.
Dismissal suppresses repeated delivery. The logic still has 5A's documented
lexical limitations: it neither understands competence nor judges correctness.

## UI and polling

LiveInterviewPage renders InterviewCopilot for both roles. Candidate rendering
contains disclosure and consent/withdrawal only. Recruiter rendering additionally
contains prepare, requirement, provisional question, short source-based reason,
dismiss/ignore and waiting/unavailable/error states. The checkbox starts unchecked
and resets on replacement. Preparation sends no consent. Default-off and
not-live-connected states are explicit. No localStorage, IndexedDB or transcript
cache is used.

Polling reads the owner's isolated HTTP endpoint; it is not the shared caption
WebSocket. It never invokes inference or persists anything. A request sequence
fence prevents responses from before a local mutation/disconnect from restoring
old data. There is at most one polling request in flight. Explicit withdrawal/decline
can supersede a slow poll; that poll then cannot restore display. HTTP calls time
out after eight seconds. Ordinary media/captions do not await assistant requests.

## Files and responsibilities

- backend/app/services/copilot_delivery.py: process-local lifecycle, epoch fences,
  bounded manager and internal synthetic seam around existing CopilotLogic.
- backend/app/api/routers/interview_copilot.py: protected HTTP boundaries and scope.
- backend/app/core/config.py, api/router.py, main.py: flag, routing, one cleanup loop.
- backend/app/services/transcript_privacy.py: storage-withdrawal invalidation hook.
- frontend/src/api/copilot.ts: validated role-specific requests and response fences.
- frontend/src/components/InterviewCopilot.tsx: consent and recruiter-only panel.
- frontend/src/components/LiveInterviewPage.tsx: panel placement, no caption changes.
- backend/tests/test_copilot_delivery.py, frontend/tests/copilot.test.ts: synthetic
  API/runtime/UI regressions; interviewFinalization test stubs include the panel.
- .env.example, compose.yaml, README and this guide: default-off configuration/status.

## Verification

See the final verification record below. API tests use the actual ASGI app and
existing authentication/ownership implementation with a transactional SQL double;
they are not a new live PostgreSQL or browser acceptance claim. No demo data,
Docker volume, external service or live configuration was changed.

## Planned 5C prerequisites — separately approved

1. Trusted F4 recognized-event adapter: real caption run, speaker/source sequence,
   original time, current revision and post-two-consent cutoff, with no pre-consent replay.
2. Fresh authorization before processing and before publication; preserve run and
   epoch checks and independent errors so captions never depend on assistant success.
3. Caption-run replacement, completion, access-loss and authoritative disconnect
   cleanup hooks. Do not broadcast suggestions to the caption room.
4. Decide and enforce deployment constraints before multiple workers/replicas;
   process-local consent must not be presented as distributed authorization.
5. Synthetic live browser acceptance proving recruiter-only payloads, both consents,
   withdrawal races, expiry and useful source-linked questions. No live provider is
   authorized by either 5A or 5B. No final F11 innovation claim until verified.


## Verification record — 19 October 2026

- Backend: **220 passed, 1 skipped** across delivery, all **72** hardened 5A
  tests, F3 invitation/scheduling, F5 pairing/mapping/evaluation, caption lifecycle,
  graceful finalization and transcript consent. The 22 delivery tests include
  real ASGI auth/ownership with synthetic SQL double, cookie isolation, protected
  mutations, changed authorization, two-party consent, no pre-consent replay,
  in-flight fencing, restart, TTL, capacity, dismissal, forged IDs/roles and the
  storage-withdrawal hook before failed deletion. No live PostgreSQL acceptance
  or distributed-consent claim is made.
- Skipped: existing test_real_caption_route_starts_two_local_workers requires an
  explicitly supplied local model. No model downloaded or worker started here.
- Frontend: **241 passed**, including 10 new request-validation, consent-control,
  candidate-isolation, withdrawal-during-slow-poll and stale-response tests.
- TypeScript build and Vite production build passed. Vite retains its warning
  about the large LiveInterviewPage bundle (LiveKit included); no unrelated
  code-splitting redesign was undertaken.
- Docker: Compose configuration validated with a synthetic process-local password
  only; **8 offline helper tests passed**. No container/image build, migration,
  volume change or live Docker deployment was needed or claimed for 5B.
- Python compilation and git diff --check passed. Private test output stays under
  ignored data/f11-5b-backend-tests.xml and data/f11-5b-frontend-tests.txt.
- Intermediate failures were resolved: the Windows no-network test guard initially
  blocked asyncio's local self-pipe; it now permits that loopback plumbing while
  blocking real HTTP transport/external connections. Two parent-component test
  mocks needed the new child component stub. Existing finalization assertions
  were preserved. Final runs have no failures.

Suggested viva explanation: the API checks who is asking and whether that person
still owns valid access; the run manager separately checks both consents and the
current generation. Polling only reads a short-lived suggestion. Withdrawal changes
that generation and clears the result, so a slow old calculation or HTTP response
cannot legitimately restore it. The model-free graph offers a question, not a
candidate judgment. Live recognition integration remains a separate increment.
