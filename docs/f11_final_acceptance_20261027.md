# F11 final bounded acceptance — 27 October 2026

Implementation baseline: `a14daa9e808c4f21966219195b29a5cb9af57289`,
`feature/office-20261026-acceptance`. No F3/F4 Cloud trial was repeated.

## Result and evidence boundaries

**Offline browser: PASS within the bounded synthetic scope**, including the
subsequent Dismiss/withdrawal closeout below at baseline `90e7418`. The first pass
was PARTIAL because the two explicit lifecycle clicks were unobserved; that
historical gap is now closed using the actual application. Media and recognition
remain simulated. Real F4-to-F11 Cloud acceptance remains unverified.

The existing Task 4C offline media module and fake AssemblyAI connector approach
were reused in an ignored, test-owned runtime. The frontend used simulated
LiveKit and generated synthetic tracks, not a real room. A deterministic fake
provider produced predefined question/answer text after receiving PCM frames.
This is not speech-recognition accuracy or bidirectional-media evidence.

Actual browser AudioWorklet delivery, authenticated FastAPI caption websockets,
AssemblyAI protocol decoding, server role/time assignment, LiveStreamingCaptions,
LiveBridge, LangGraph, API authorization and React rendering remained in use.
There was no public text-ingestion endpoint or mocked frontend API response.
No model inference, external socket, real SMTP or physical device was used.

## Observed workflow

1. Reused the explicitly owned synthetic PostgreSQL lab at schema
   `0017_booked_interview_email`; preserved its earlier records. Added one fictional
   recruiter, approved Python requirement, saved eligible application, booking and
   invitation. No preserved database migration or old invitation reuse occurred.
2. Recruiter signed in using Edge. Candidate claimed its private invitation in
   Chrome without recruiter login. The distinct browser families isolated cookies
   on the new test origin; existing application/browser origins were untouched.
3. A preliminary offline run recognized the scripted context before both assistant
   consents. No suggestion appeared. It was preserved as pre-consent exclusion,
   not positive acceptance. Bounded expiry subsequently removed active controls.
4. For the positive offline run, recruiter opened the caption socket, prepared the
   caption-bound assistant run, and both roles independently checked and accepted
   F11 consent. Candidate then separately accepted caption processing, opening
   two-party capture. Transcript storage remained disabled throughout.
5. The trusted streaming path broadcast a recruiter question and candidate answer
   with server-assigned roles, original sequences 1/2 and approximate 8/10-second
   capture intervals. The real graph generated the recruiter-only provisional
   question: “Could you walk through a concrete example related to this
   requirement: Python?” Its card identified Python and source events 1/2, with
   an explicit lexical-association/not-competence warning.
6. Sanitized actual HTTP response observations recorded three recruiter responses
   containing a suggestion and five candidate responses within 2.5 seconds of
   those observations. Candidate responses contained no suggestion, processing or
   exploration fields. The candidate DOM contained consent controls, not the
   provisional question or private reasoning. Shared captions remained separate.
7. **First pass, historical:** the suggestion disappeared under its short lifetime; the recruiter
   later displayed `Assistant: withdrawn`. No suggestion remained. An attempted
   Dismiss observation missed the bounded card, and an attempted explicit
   withdrawal missed expired controls. Both are **UNOBSERVED in the browser**.
   Both participants left the simulated interview. Candidate terminal wording
   was not independently confirmed to match the recruiter simultaneously.
   The later lifecycle closeout below supersedes these two unobserved outcomes.
8. An exact-interview database check found **zero transcript sessions**. F11 has
   no transcript/suggestion table or persistence writer; its bounded state is
   process-local. Test evidence stores sanitized metadata, not application
   transcript content or raw API bodies.

Ignored evidence locator: `data/f11-final-current.json`. The directory contains
`api-metadata-main.jsonl`, `api-reconciliation.json`, `browser-results.json`,
`no-storage.json`, focused test output and test-resource ownership records.
No private identity, credential, invitation URL or recording is committed.
After verification, both simulated browser participants left, and only the
test-owned frontend, API and reused test database were stopped. The named volume,
earlier synthetic records and ignored evidence remain. Working Groq container
identities and start times matched their preflight snapshot.

## Browser lifecycle closeout — 27 October 2026

Verified clean branch/HEAD `90e7418447ba8d3782327eac057ae2368293df14` before work.
Reused the same owned containers, database, fictional booking, current candidate
session and existing offline browser setup. The join window remained open; no new
application, booking, invitation, database or migration was needed. A fresh F11
run received independent consent through the existing recruiter/candidate UI.

- **Dismiss PASS:** the real recruiter card appeared. The existing test-owned
  response observer held one actual suggestion GET reply for four seconds, without
  changing its contents. The recruiter clicked **Dismiss / Ignore** while that
  request was pending. The card cleared and stayed absent after the held reply
  and subsequent polling. The authenticated Dismiss response contained no
  suggestion. No automatic Dismiss retry occurred.
- A replacement assistant context within the same caption run produced no fresh
  card before the normal caption limit. That intermediate result was preserved;
  no timeout was extended or question forced. Only the isolated backend was then
  restarted for a fresh offline caption run, reusing the same valid booking.
- **Withdrawal PASS:** after fresh independent F11/caption consent and another
  trusted fake-recognition question/answer, the real card appeared again. A second
  actual suggestion GET was held for four seconds. Recruiter clicked **Withdraw
  assistant consent** while it was pending. After the reply and ten seconds of
  further polling, the card remained absent and **both browsers** displayed
  `Assistant: withdrawn`. Candidate DOM and actual API observations continued to
  omit private suggestion, processing and exploration fields.
- **F4 unaffected:** the real caption component remained active after F11
  withdrawal. Sanitized fake-provider metadata recorded new finalized events from
  both roles after the withdrawal response. These were simulated recognition
  outputs through the unchanged authenticated F4 path, not external recognition.
- **No storage:** the exact interview still had zero PostgreSQL transcript
  sessions; there was no co-pilot persistence table. Application F11 state remains
  transient; test evidence contains only bounded status/count metadata.

The latency holds are confined to the already ignored evidence adapter. They do
not fabricate API bodies, bypass authorization, change F4 or expose a new route.
The ordinary database locks serialized the held GET before the mutation response;
this proves the browser handles an older request already pending at the click,
not a claim that a server read occurred after withdrawal was committed.

Evidence in the same ignored directory: `dismiss-browser.json`,
`withdrawal-browser.json`, `api-metadata-lifecycle.jsonl`,
`api-metadata-withdrawal.jsonl`, `withdrawal-f4-metadata.jsonl`,
`lifecycle-reconciliation.json` and `lifecycle-no-storage.json`.
All successful browser-result checks and API reconciliation checks passed.
Only the adjusted ignored adapter's Python compilation was checked; the previous
184 backend/19 frontend tests and build were not unnecessarily repeated. No
application source change was needed. Both simulated participants left; test-owned
services were stopped, earlier evidence/volume preserved and Groq unchanged.

## Confirmed correction and compatibility

The current AssemblyAI live stream **already uses**
`CaptionSession._publish_caption`, which offers finalized events to LiveBridge
before the unchanged caption broadcast/storage path. A new fake-WebSocket test
exercised actual AssemblyAI decoding through this hook, the real graph and private
delivery without storage. No F4 transport, timestamp, consent or persistence
algorithm changed.

The confirmed defect was F11 source disclosure: only fixed AssemblyAI replay was
identified as cloud-originated. Live AssemblyAI mode could display “Local F4
adapter enabled” and the local-source disclosure. Regressions failed before the
correction. F11 configuration now exposes a non-sensitive `live_cloud` boolean;
the API client validates it, rejects conflicting modes, and the UI distinguishes
generated-track cloud captions from fixed server-owned replay and local STT.
It retains independent assistant consent and describes the possible upstream
model-training use. No flag is enabled by default and no consent is inferred.

The first offline setup used a loopback media URL with a named localhost origin,
which the existing frontend URL policy rejected. The ignored configuration was
aligned with the historical Task 4C cloud-shaped placeholder; no network request
used it and the application URL policy was not relaxed. A further transient
recruiter access failure was not attributed to a production defect. No general
F3 recovery or configuration change is claimed.

## Focused verification

- **184 backend tests passed, 0 failed/skipped**: model-free graph and prefaced
  questions, delivery/API consent and ownership, LiveBridge, and AssemblyAI live
  adapter/session regressions. This includes the new live-cloud disclosure and
  streaming-final-to-graph tests. Preliminary/regression runs are not added again.
- **19 frontend tests passed, 0 failed/skipped**: role-specific response validation,
  independent consent, source wording, source-flag validation, response fences,
  private candidate projection, dismissal during a pending poll, withdrawal,
  disconnection and result expiry. These are component/transport tests, not extra
  browser observations.
- Existing focused service tests cover stale criteria/requirements/session identity,
  access loss, pre-consent audio, incomplete/irrelevant/ambiguous evidence,
  withdrawal during calculation, replacement, expiry and finalization. They
  abstain or clear output rather than inferring a candidate failure.
- TypeScript, production frontend build and whitespace checks passed. The existing
  large LiveInterviewPage bundle advisory remains; no UI/bundling redesign.

## Original innovation rationale

TalentTrace AI's Dynamic Interviewer Co-Pilot addresses a narrow problem in the
recruiter workflow: a recruiter must listen to an answer, remember the approved
job requirements, and decide whether a useful follow-up is needed. A static
question checklist cannot respond to what was just said. A general chatbot can
respond fluently, but may invent missing evidence, make unsupported technical
judgments, or introduce additional model cost and privacy exposure. This project's
innovation is a small, inspectable decision workflow that reacts to authorized
conversation evidence while leaving the interview and every hiring decision with
the human recruiter. It is a project-specific contribution, not a claim of a
world-first invention.

The implementation combines three existing project capabilities rather than
adding another AI provider. Approved requirements supply the job context. Trusted
F4 recognition supplies speaker-attributed, timestamped events. A model-free
LangGraph workflow validates context, assembles dialogue, tracks exploration,
selects a possible follow-up, and validates the output. A question followed by a
lexically related answer may justify inviting a concrete example. The system does
not infer that the candidate lacks knowledge simply because an example has not
yet appeared. If the evidence is unfinished, ambiguous, unrelated, out of order,
or insufficiently grounded, waiting or abstention is the intended result.

Consent and delivery are part of this design. Each participant independently
authorizes assistant processing for the actual caption-bound run. Caption consent
and optional durable storage consent remain separate. Recognition that predates
assistant consent cannot be replayed into a later authorized context. Only the
recruiter receives the proposed question and its requirement association; the
candidate receives the controls needed to understand and withdraw processing,
without private suggestion or exploration fields. Bounded memory, short expiry,
generation fences and fresh access checks limit stale advice after changing
requirements, withdrawal or disconnection.

This makes the feature understandable in a viva and affordable in the intended
demonstration environment: no extra inference call, combined score or automated
selection policy is required. Its tradeoff is deliberately limited language
coverage. Literal associations may miss valid paraphrases, and a relevant
follow-up is not evidence that an answer is correct. The demonstrated value is
timely, source-linked question assistance with conservative uncertainty and
human control. Real-provider recognition quality, usefulness across diverse
interviews, and observed live latency require further acceptance beyond this
bounded synthetic test.

## Viva explanation and remaining limits

“F4 recognizes speech; F11 runs deterministic graph rules over authorized events.
It can suggest a follow-up linked to a requirement, but it does not understand or
grade the candidate's technical competence. The recruiter can ignore it.”

Single-process, single-caption-room bounds and literal matching remain. Concurrent
role results arriving out of order can be conservatively rejected. Polling means
cross-browser clearing is not instantaneous. Already delivered information cannot
be remotely erased; clearing references is not memory zeroization. Restarts lose
assistant state. A positive offline question is not real F4-to-F11 Cloud acceptance.
Do not claim measured live latency, arbitrary speech coverage, multi-worker
deployment readiness from this bounded synthetic acceptance.
