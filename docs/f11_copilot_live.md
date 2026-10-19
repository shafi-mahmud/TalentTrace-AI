# F11 Increment 5C: trusted F4 recognized-speech integration

## Status and activation gate

Implemented on `feature/f11-copilot-live-integration`, based on 5B `8c3957e`.
**Automated synthetic integration only; live browser acceptance NOT performed.**
No final Innovation Feature acceptance or measured live-latency claim is made.
No existing runtime, secret configuration, database or model has been changed.

Both INTERVIEW_COPILOT_ENABLED and INTERVIEW_COPILOT_LIVE_ENABLED default false,
including Docker Compose. The original development-only synthetic LiveKit,
caption model, websocket origin and participant authorization gates still apply.
No additional STT pipeline, LLM, inference provider or persistence is introduced.

## Actual execution flow

1. Existing caption websocket authenticates the recruiter-owned interview or the
   candidate session, validates origin and joining window, and connects one role.
2. CaptionSession owns a fresh nonpersistent caption_run_id UUID. On two-party
   caption consent, the existing local workers start and the session records its
   monotonic audio origin plus a corresponding wall-clock origin.
3. When live F11 is explicitly enabled, a LiveBridge attaches internally. The
   recruiter prepares an F11 run pinned to this actual caption UUID; it does not
   invent a saved-transcript capture ID. Both participants independently accept
   F11 for this run. Caption/storage consent still does not imply F11 consent.
4. CaptionSession._decode awaits the existing local recognizer, validates text,
   assigns its original role and global sequence, then synchronously offers the
   event to the bridge before the unchanged shared caption broadcast/storage.
   This is the only production source hook. No browser text-ingestion route exists.
5. The bridge keeps at most 15 events / 12,000 characters, and waits for a settled
   snapshot. It rechecks both websocket authorizations and the existing F11 API
   ownership/session/revision/privacy scope before offloading the original graph.
6. After calculation, it checks authorization again before publishing under the
   same run, epoch and current-context generation. The recruiter polls the private
   HTTP endpoint. Shared captions and candidate status contain no suggestions.

The 5A LangGraph stages remain validate_context, assemble_dialogue,
track_exploration, select_follow_up and validate_output. Original bounds,
three-second settling, cooldown, deduplication and independent evidence checks
remain. A new recognized event immediately hides the old suggestion while its
new context waits or abstains. Explicit uncertainty and unrelated answers are not
candidate failures and cannot justify competence judgments.

## Source identities and no pre-consent replay

Each internal Event preserves Source(caption_run_id, original recognition
sequence), the authorized speaker role and original audio_start_ms/audio_end_ms
(rounded to milliseconds). Its ordering timestamp maps the audio end into the
F11 run-relative clock. The original caption JSON start/end remain unchanged.
These are approximate chunk boundaries, not word-level timings or persistent IDs.

The bridge accepts only its own caption UUID and monotonically increasing
sequence/end-time. Duplicates, stale sequence, wrong-run or backward audio times
are ignored. Concurrent role workers may finish out of audio order; conservative
rejection can lose usable context rather than guess a reordered association.

Eligibility uses the **start of the original audio chunk**, compared with the
instant both F11 consents became active (rounded upward, never downward). A
chunk crossing the consent boundary is discarded in full, even if recognition
returns after consent. No pre-consent captions are buffered for later replay.
F11 replacement/withdrawal clears its history; original source sequences are not
rewritten. The Update synthetic flag reflects this restricted synthetic-demo
runtime; it is not proof that arbitrary microphone input is synthetic.

## Bounded work, failures and lifecycle

There is at most one pending worker task per bridge and one global graph execution
slot across caption-run replacements. Later events replace the pending snapshot;
there is no per-event queue. The graph runs off the event loop, never awaited by
F4 decoding/broadcast/storage. Cancellation fences output; the bounded calculation
may finish and release its processing slot, but cannot publish stale results.
No raw audio enters the co-pilot. No extra transcript, event or suggestion is
written to PostgreSQL, disk or logs. LangSmith export remains disabled by 5A.

F11 withdrawal, durable storage withdrawal and run expiry notify the bridge to
clear its bounded context. Caption stop, access-monitor failure, normal finish
and caption-run replacement invalidate co-pilot consent and output. Caption
finalization closes F11 before draining the existing storage path; F4 may still
save its separately authorized final transcript normally. Assistant setup, offer,
worker or authorization failures fail F11 closed and do not stop F4. A stopped or
failed adapter requires a fresh authorized caption run; preparation refuses it.

Fresh DB-derived authorization is checked before graph processing, again before
publication, and on recruiter retrieval. API row-lock conventions from 5B remain.
Revoked candidate sessions, expired joining windows, changed criteria and withdrawn
storage cannot authorize old results. A late network response cannot be remotely
erased, so the UI also fences old requests, clears on leave/withdraw and polls
status. Cross-browser clearing is observed on the next poll; do not describe it as
a push notification with zero network delay.

Process-local consent is still single-backend-process only. F4 still supports a
single caption room and its existing two-minute limit. Restart loses all F11
consent and context. Python reference release is not memory zeroization; bounded
in-flight local calculation can briefly retain its inputs until it finishes.

## Files changed

- backend/app/services/copilot_live.py: trusted adapter, ordering/cutoff, bounded
  offload, pre/post authorization and lifecycle cleanup.
- backend/app/services/interview_captions.py: actual caption UUID/origin, guarded
  recognition offer, stop/finalization invalidation; broadcast contract unchanged.
- backend/app/api/routers/interview_captions.py: optional adapter attachment and
  existing recruiter/two-websocket authorization callbacks.
- backend/app/services/copilot_delivery.py: actual caption binding, live publication
  fence, invalidation listeners, rounded-up consent cutoff and live status/reason.
- backend/app/api/routers/interview_copilot.py: gated preparation against the actual
  current caption session, configuration status; no new ingestion endpoint.
- backend/app/schemas/interview_copilot.py: optional original audio interval fields.
- backend/app/core/config.py, .env.example, compose.yaml: second default-off gate.
- frontend/src/api/copilot.ts, components/InterviewCopilot.tsx: validate/display
  actual adapter status without claiming recognition or semantic success.
- backend/tests/test_copilot_live.py, tests/test_copilot_delivery.py,
  frontend/tests/copilot.test.ts: integration and role/status regressions.
- README.md and F11 documentation: current scope, gate, evidence and limitations.

## Read-only runtime readiness — 19 October 2026

The existing talenttrace-docker-demo db/backend/frontend containers are healthy;
frontend is bound only to 127.0.0.1:5188. Their current images predate this increment;
source changes were not deployed to them. The restricted nginx API proxy already
supports websocket upgrade and disables buffering.

Actual backend inspection: livekit Python module is installed; faster_whisper is
**not installed**; no LOCAL_CAPTION_MODEL_PATH is configured. LiveKit synthetic
mode and both F11 flags are OFF. Compose defines no local LiveKit service, no
model mount and only private/internal backend networking. The separate pinned
backend/requirements-stt.txt exists, but has not been installed in this image.

Therefore **the browser activation gate is BLOCKED**, not ready for an immediate
live interview. Participant authorization, current processing consent, recognized
speech and observed latency have not been established for a 5C browser runtime.
No model downloads, package installs, new services, account provisioning, booking,
media, email, Groq or publication occurred during this increment.

## Required next approval and controlled acceptance procedure

Recommended next step, not executed: approve a disposable single-worker runtime
plan with a reachable supported local LiveKit instance, the existing pinned STT
worker dependencies, an explicitly provided local model mounted read-only, and
both default-off flags deliberately enabled. Preserve all existing demo volumes.
Browser media/network routing must be verified rather than assuming container
loopback refers to the laptop. Do not weaken browser HTTPS/security checks.

Only after that readiness check and explicit activation approval:

1. Provision one supported disposable synthetic interview and separate authorized
   recruiter/candidate browsers; use generated WAV speech, no physical microphone.
2. Establish both caption sockets/temporary caption consents. Prepare the assistant
   run for that real caption session; each independently accepts F11 disclosure.
3. Wait for both F11 consents, then play the synthetic Python question/answer.
   Allow a new full audio chunk after consent; do not replay earlier captured audio.
4. Observe actual speaker-attributed F4 recognized text, then the recruiter-only
   provisional question. Inspect candidate API/shared websocket payloads for absence
   of suggestions or private coverage. Record observed end-to-end latency.
5. Play a subsequent relevant example; verify the old question clears/changes.
6. Withdraw F11; verify no further processing/output. Finish captions normally;
   verify a fresh run never inherits consent or context.

If ASR or lexical association is insufficient, report abstention honestly. No
provider request or loosened grounding is authorized to force a successful demo.


## Verification record

- Backend: **237 passed, 1 skipped**, including all **72 hardened 5A tests**,
  the 22 existing delivery tests and **17 new live-adapter tests**, plus F3/F4/F5
  scheduling/access, pairing/mapping/evaluation, captions, finalization and consent.
- New tests invoke the actual CaptionSession._decode hook with mocked recognizers,
  then the actual adapter and graph. They verify private source-linked Python
  suggestions, later SQL exploration, uncertainty/unfinished/unrelated abstention,
  pre-consent cutoff (including submillisecond rounding), speaker/timing identity,
  duplicates/out-of-order/wrong runs, bounded overflow, slow/failing graph isolation,
  withdrawal, fresh authorization before publication, finalization and storage.
  They also exercise live preparation through real HTTP auth with a SQL double.
- Skipped: existing real caption-worker test requires an explicitly supplied local
  model. No real Whisper worker or live media was started in this increment.
- Frontend: **242 passed**; TypeScript and production Vite build passed. The
  existing large LiveInterviewPage chunk warning remains.
- Docker: Compose configuration validation and **8 offline helper tests passed**;
  no image build, restart, volume mutation or migration was performed.
- Python compilation and git whitespace checks passed. Private test records are
  ignored under data/f11-5c-backend-tests.xml and data/f11-5c-frontend-tests.txt.
- Initial failures were resolved: an old 5B static assertion forbade any router
  reference to co-pilot code and was replaced with a no-public-submission check;
  runtime payload tests still assert unchanged candidate caption fields. The graph
  failure test now verifies the actual safe contract (withdrawn/cleared F11, F4
  continues), rather than requiring the entire adapter object to close permanently.
  Final runs contain no failures.

These results verify integration plumbing with synthetic recognition fixtures,
not microphone/WAV-to-Whisper live behavior. No observed suggestion latency or
successful browser innovation demonstration is claimed. F11 remains **PARTIAL:
implemented adapter, live acceptance blocked by the documented runtime gate**.

Implementation commit: `39188217d29928e2a9494592cfd512a84d38421a`.
