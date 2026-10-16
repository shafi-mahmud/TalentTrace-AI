# Milestone 3 interview analysis

## Integration hardening update (16 October 2026)

Current work is on `feature/milestone3-integration-hardening`, based on `a3b6dcd`.
The earlier sprint observations below are historical, not claims of a newly
completed live interview. See [local live rehearsal](milestone3_local_live_rehearsal.md),
[curated references](technical_reference_grounding.md) and
[durable analysis](durable_interview_analysis.md) for the new implementation.
Current migration head is `0014_interview_analysis`, tested only on disposable
PostgreSQL. Existing demo databases remain unchanged.

The graph now defaults to attributed official-document summaries. Analysis can
opt into PostgreSQL identities, leased attempts and privacy-bound results.
Exact connectivity checks are excluded from technical Q&A; interrupted answers
remain uncertain. Source arrival order is normalized by capture/sequence before
pairing/fingerprinting, without rewriting text or IDs. Semantic requirement
coverage remains conservative: paraphrases without literal evidence are labelled
unassessed, not proof of missing skill. No automatic hiring decisions are added.

Latest checks: 156 focused F4/F5/real-PostgreSQL tests passed before additional
recovery cases; six expanded durable PostgreSQL scenarios then passed, including
an independent interpreter and cleanup failure. Broad backend regression passed
1,301 tests with 72 optional skips after preparing the worktree-local MCP runtime.
Later source-order/Q&A regressions passed 52 with six PostgreSQL gates off in
that focused command. Frontend: 184 tests, TypeScript and production build passed.
The existing >500-kB LiveKit chunk warning remains. No new live provider request
has run at this checkpoint. Full browser capture-to-evaluation remains unverified.

## Earlier milestone baseline

Implemented on `feature/milestone3-interview-evaluation`, based on `9c6b255`.
Existing F4/demo/intake worktrees and their databases are not activated or changed.

## Requirements and scope

The official local BID (cover version 1.0, filename
`Final_Project_doc_Business_Info_Document_AI_Recruitment_Platform_v2.pdf`)
pages 13–14 requires Q&A association, relevance, factual/technical accuracy,
completeness, articulation, requirement coverage and source-backed justification.
Page 21 requires meaningful LangGraph orchestration. No trainer-authored F5
clarification was found. Numeric comprehensive interview scoring is stretch F9;
consolidated reporting/export/comparison is F6, not implemented by this sprint.
No weights or automatic hire/reject decision are invented.

## Implemented execution

`PostInterviewInputService` authenticates current recruiter ownership and current
confirmed job revision; locks the interview privacy row; refuses revoked,
expired, missing-retention, incomplete, failed or inconsistent transcript data.
Only finalized, speaker-labelled accepted-audio captures are used. This does not
certify full-interview capture or ASR accuracy.

The actual LangGraph has these nodes and edges:

1. `pair_questions`: conservative deterministic question detection, source-linked
   candidate answer aggregation and explicit uncertainty.
2. `map_requirements`: literal matching to existing confirmed criterion IDs.
3. `retrieve_technical_references`: explicit small synthetic lexical reference
   provider, separate from Company Policy retrieval.
4. `assess_answers`: actual configured Groq structured-JSON generation.
5. `validate_evidence`: schemas, question identities, exact transcript quotations,
   role/pair associations, four distinct dimensions and technical citations.

`START -> pair -> map -> retrieve -> assess -> validate -> END`.
Grounding validation can route back to assessment once with a repair instruction;
a second invalid result fails. No retry occurs after timeout/provider failure or
unparseable structured output. Groq SDK retries are disabled. Each request has a
45-second timeout, the operation has a 110-second deadline, and graph recursion
is bounded. No checkpoint containing transcript text is written. External
LangSmith tracing settings cause an explicit refusal before graph execution.

Q&A IDs derive deterministically from interview/question turn UUIDs. Questions
and answers remain exact source text; timestamps remain capture-relative. Answers
can span multiple turns. Follow-up questions become separate items. Candidate
clarifications are not silently turned into answers. Recruiter interruptions and
multipart questions require review. Unanswered questions are not incorrectness.
Unpaired source turn IDs remain visible; conversation outside these conservative
patterns is not claimed to be semantically resolved. Simultaneous/ambiguous speech
and follow-up relationships need human review; no semantic pairing model exists.

Requirement mapping is **literal topic coverage**, not proof of skill. It returns
partial, uncertain or not_evidenced, original criterion IDs, Q&A/turn references,
an explanation and a suggested follow-up. Negation/uncertainty remains in source
and flags uncertainty. Synonyms and complex multiword requirements can be missed;
absence of a literal match is not absence of a skill. Suggestions are not answers.

## Rubric and technical knowledge

`interview-evidence-v1` is a qualitative, provisional versioned implementation
choice: supported, partial, concern, uncertain, not_assessed. It has no numeric
score or weights. Each answer has relevance, technical_accuracy, completeness and
articulation with justification and transcript evidence. Articulation is text
organization only, never accent/personality/protected-trait assessment.

Substantive judgments require candidate evidence from the same Q&A; technical
accuracy additionally requires an exact supplied technical-reference citation.
Without that basis accuracy must be uncertain/not_assessed. Unanswered questions
cannot be assessed as a negative outcome. Uncertain pairing cannot receive
supported status. Exact quotations verify provenance, **not** semantic entailment,
factual correctness of all model prose or freedom from bias. Recruiter review is
mandatory; strengths are labelled AI interpretations, not validated qualifications.

Technical Reference RAG is a minimal replaceable boundary with three explicitly
synthetic demo facts (Python collections, transactions, HTTP). It is not a full
approved technical corpus, semantic/vector RAG or exhaustive accuracy oracle.
The BID did not establish a mandatory Technical Knowledge corpus in the inspected
pages; the planned architecture proposes conditional technical retrieval. A
reviewed real technical corpus and retrieval/citation evaluation remain work.

## API, privacy and lifecycle

Disabled by default; development environment only. Require explicit
`INTERVIEW_EVALUATION_ENABLED=true`, `TRANSCRIPT_STORAGE_ENABLED=true`, configured
`GROQ_API_KEY`/`LLM_MODEL`, and exact operator-reviewed synthetic job UUIDs in
`INTERVIEW_EVALUATION_SYNTHETIC_JOB_IDS`. The server allowlist cannot be overridden
by a client-supplied synthetic flag. The UI presents a separate unchecked external
processing disclosure. This is not authorization for real interview processing.
Before production/real-data use, settle candidate-facing disclosure, consent and
human review requirements; storage consent alone is insufficient.

- `GET /api/v1/interview-analysis/config`: availability and disclosure only.
- `POST /api/v1/jobs/{job}/interviews/{interview}/analysis`: body
  `{ "operation_id": "<new UUID>" }`, existing recruiter cookie,
  `X-TalentTrace-Request: 1`, `X-TalentTrace-Job-Revision: <current revision>` and
  `X-TalentTrace-Evaluation-Disclosure: synthetic-interview-analysis-v1`.
  Returns HTTP 202 and an operation status, not assumed analysis success.
- `GET /api/v1/jobs/{job}/interviews/{interview}/analysis/{operation}`:
  authorized status/result; never invokes a model.

No schema migration is needed: results are ephemeral process memory, not database
persistence. One active analysis at a time, at most 20 retained operations,
ten-minute maximum lifetime, five-second privacy/expiry maintenance. Require one
backend worker. Same operation UUID/input is reused; a conflicting UUID is refused.
New UUIDs for the same completed/running input also reuse work within this worker.
No cross-worker/durable idempotency is claimed. Restart/expiry loses operations
and yields 404; do not automatically repeat a POST after uncertainty.

Input authorization/fingerprint is rechecked immediately before model work,
after inference, and before every result GET. Revocation, retention expiry,
source deletion or source/revision change prevents result disclosure; result text
is discarded. Background maintenance discards unavailable results and cancels
remaining work. Shutdown cancels tasks and clears memory. No database-derived
assessment survives deletion because no such persistent store exists. Already
delivered text or an already-authorized provider request cannot be recalled;
the UI clears results when its next two-second status poll detects loss of access.
Future persistent assessments need durable invalidation/deletion and concurrency
protection; they cannot reuse RAM idempotency as a production guarantee.

The existing API no-store, authentication, CSRF/origin protections apply. Model
input is minimized to synthetic criteria/Q&A/turn evidence and demo references,
without candidate emails/CVs or login credentials. No prompts/transcripts/provider
bodies are logged. Provider exceptions become fixed error codes. GET navigation,
status polling and opening saved results cannot silently trigger inference.

## Reviewer UI and rehearsal

Open Interview Scheduling, select the existing synthetic job and open its saved
interview (or historical transcript/privacy view). The recruiter-only analysis
panel is separate from media and optional storage. Review the synthetic external
processing disclosure, check the box and click **Analyze finalized interview**.
Follow status using **Check analysis status**; no automatic POST retry. Results
show original statements, speaker/turn citations, pairing warnings, four AI
dimensions, literal requirement coverage, strengths, gaps, follow-up suggestions
and explicitly synthetic technical references. No model result is displayed until
the backend reports completed with validated output. Candidate UI has no panel.
Each requirement also shows its linked per-answer dimension justifications;
this is not a separately inferred requirement pass/fail or skill score.

Use only a fresh disposable database through migration 0013, private synthetic
fixtures and unused loopback services. No existing F4/intake data should be used
for this development demonstration. The private rehearsal helper uses the real
login endpoint and normal authenticated analysis API; it does not bypass auth.
It seeds explicitly synthetic finalized transcript fixtures, **not** a claimed
new live interview/transcription run. No microphone, real media or LiveKit
verification is implied by the analysis rehearsal.

### Repeat the isolated analysis demo

Prerequisites: Docker running with the existing cached PostgreSQL test image and
the stopped local F4 container metadata used by the transcript test fixture;
existing Python backend/test dependencies; offline-installed frontend packages;
ports 54402, 8022 and 5190 unused. The helper reuses those test fixtures, not an
arbitrary configured database, and creates/removes its own PostgreSQL container.
It is a developer rehearsal, not a clean-machine production launcher.

In this branch's `backend` directory, with the existing Python environment:

```powershell
python tests/run_milestone3_demo.py --env-file '<existing-private-env-file>' --confirm-free-tier-synthetic
```

Only the existing key/model are read from that private file; its database, email
and other settings are not loaded. No inference starts during seeding. The helper
creates a fresh private login under this worktree's ignored `data/milestone3`.
It enables only its new synthetic job, disables email/media tokens, uses one
worker and enforces a 30-minute maximum backend lifetime. Ctrl+C removes its
disposable database. Starting another instance while 54402 is occupied refuses
instead of taking over an existing service.

In a second terminal in `frontend`:

```powershell
$env:VITE_API_BASE_URL = ''
node node_modules/vite/bin/vite.js --config vite.milestone3.config.ts
```

Open `http://127.0.0.1:5190/`, sign in with the generated private login, then
follow the reviewer sequence above. Only clicking the disclosed analysis action
can call Groq. This incurs free-tier quota usage, so do not repeatedly generate
new operations. Use the same operation/status after uncertain delivery. Stop
both temporary processes when finished; do not open a public tunnel.

## Verification and remaining work

One real standalone Groq graph run used two fictional Q&A items and
`openai/gpt-oss-120b`: grounded output passed, incorrect Python immutability was
flagged as technical concern, unanswered question dimensions remained
not_assessed. A separate real authenticated HTTP run returned 202 then completed
in approximately 4.1 seconds, with one Q&A, one requirement and four dimensions.
An identical completed-operation request reused the result. These were approved
free-tier synthetic tests; mocked tests are not counted as real inference.

Focused tests include normal/multiturn/follow-up/unanswered Q&A, interruption,
clarification, fabricated/wrong-role evidence, literal gaps, negation, synthetic
retrieval, real LangGraph routing, controlled grounding repair, provider failure,
unsupported technical citations, no auto-exclusion, tracing guard, API auth,
allowlist/revision/incompleteness, deduplication, mid-call withdrawal and transcript
deletion invalidation. Frontend tests cover explicit unchecked disclosure, retained
operation identity, one user-triggered POST, read-only polling and failure states.
Final counts and browser observations are recorded in the sprint report below.

### Actual recruiter browser rehearsal

The owner signed in with a fresh disposable recruiter account at loopback 5190,
using a separate backend on 8022 and the fixture database on 54402. A temporary
same-origin Vite proxy resolved an initial runtime CORS mismatch; a fixture title
was aligned with its confirmed snapshot so the existing job-view validator could
return it. Neither correction changed existing demo data or authorization rules.

Through the actual UI: Interview Scheduling -> select the synthetic job -> Open
interview -> independently unchecked synthetic-analysis disclosure -> Analyze.
The UI displayed the completed **real Groq** result, reused from the prior API
operation: technical concern, all four dimensions, quotations, requirement
coverage, strengths/gaps/follow-ups, original recruiter/candidate role labels and
the explicitly synthetic reference. Opening/checking the result did not start a
new model request. This was a real authenticated React/FastAPI analysis rehearsal,
not a mocked frontend assessment. Input transcript rows were explicit synthetic
fixtures, not a live recording/transcription run.

The recruiter then withdrew storage consent through the actual privacy UI. The
page reported **Deleted — verified**, the derived analysis disappeared, and
subsequent status checks remained unavailable without a model request. A stale
interview-page sentence claiming no saved transcript existed was corrected to
distinguish no audio/video recording from separately consented text storage.

LiveKit media, microphones, physical devices and newly captured Whisper speech
were **not** exercised in this sprint. Full interview-to-storage browser rehearsal
remains unverified; earlier real local Whisper/ASGI tests are separate evidence.

### Final validation

- Full backend run: 1,283 passed, 66 skipped with optional environment gates off.
  Additional edge-case tests were then added and checked in the focused run.
- Final relevant F4/F5/analysis run with disposable PostgreSQL enabled:
  **196 passed**, no failures/skips. It includes actual migration
  upgrade/downgrade/re-upgrade and privacy/concurrency tests, not live provider
  calls in automated tests. A new saved-job UI fixture check initially failed
  because its dependency was not wired to the disposable database; the override
  was corrected and the final run passed. No application authorization was relaxed.
- Frontend: **181 passed**, TypeScript and production build passed. The existing
  large LiveKit bundle warning remains. Python compilation/diff checks passed.
- The reusable launcher/proxy smoke test returned HTTP 200 for health, real
  synthetic login and owned-job loading; no analysis POST or model call occurred
  during that smoke check. Its short configured deadline exercised automatic
  shutdown/removal of the disposable container.
- One linear migration head remains `0013_transcript_lifecycle`; no new migration,
  demo activation or existing demo database change occurred.

Remaining before the final demonstration: full F4 two-browser/LiveKit/storage
rehearsal, longer interview reliability/ASR review, better semantic Q&A association
and coverage, a reviewed technical corpus, production disclosure/privacy decisions,
durable operations/results if required, meaningful recovery/checkpoint policy,
F6 consolidation/export/comparison, and reviewed integration/container startup.
No merge, push, demo migration, email, booking or production activation occurs.

## 16 October 2026 — actual saved-capture evaluation diagnosis

**Live verified:** synthetic browser F4 capture finalized as drained/saved; four
retrievable timestamped turns, two per speaker. Recognition was imperfect. This
is accepted-audio evidence, not a complete or verified-accurate interview.

**Live F5 outcome:** one authorized analysis operation failed at LangGraph
`validate_evidence` with `evaluation_output_not_grounded`. The implemented graph
reaches that code only after the initial model response and its single repair
response both fail semantic grounding. The operation retained no result. The
specific validation rule and raw responses were not retained, so the exact
original violation cannot honestly be reconstructed. Source preparation found
one uncertain Q&A and one technical reference; this does not establish which
contract the model violated. Conservative uncertain/not-assessed output is
supported and does not imply candidate rejection.

**Implemented correction:** repair receives an allowlisted fixed validation-rule
code; exhausted repair exposes the final safe rule through existing operation
error persistence. No raw response, transcript text or exception inputs are
added to diagnostics. Quote, citation, pairing and authorization checks remain
unchanged. This corrects lost diagnostics and generic repair feedback; it does
not prove the earlier model output was otherwise valid or guarantee retry success.

**Validation:** 46 focused evaluation, Q&A, mapping, reference and API tests passed;
7 optional database tests skipped. Compilation passed. All provider calls in
these tests were mocked. No new live provider request was made.

The disposable backend/database reached its scheduled 18:21:59 shutdown.
Successful capture plus failed operation were preserved in a verified private
custom PostgreSQL backup before shutdown. Do not recreate fixtures in place of
that actual evidence or retry automatically. A future explicit UI retry requires
a safely restored isolated environment and renewed user authorization; preserve
the failed-attempt backup because retry updates the same durable operation.

**Verdict: PARTIAL.** F4 saved capture is live verified; successful grounded F5
analysis remains unverified. No F6 work or production activation is implied.

## 16 October — uncertain pairing recovery

**Verified persisted state:** restored operation subsequently reached attempt 4,
failed with `evaluation_invalid_model_output`. The baseline archive had attempt
1. Thus three explicit retry attempts were accepted after restoration. Current
schema stores only the latest attempt; earlier retry errors and exact cumulative
provider call counts cannot be reconstructed. Do not infer a fresh invocation
from a displayed error alone. The latest attempt's schema failure can occur on
the initial or repair call (one or two calls); exact count is unavailable.
A private verified backup preserves this later failure and original F4 capture.

**Rule preserved:** `evaluation_pairing_requires_review` is raised when an
uncertain Q&A pair receives a `supported` model dimension. Its appearance after
repair indicates that response still violated this conservative contract; it is
not candidate rejection. The actual ASR question lacks question punctuation and
has `asr_question_form_requires_review`; a separate fragment contains its Python
context. Source text was not rewritten or combined into a fabricated answer.

**Implemented:** ambiguous pairs receive deterministic `not_assessed` dimensions
and original question/answer turn references, without model assessment. Confident
pairs still use the model and unchanged quote/citation validation. Mixed results
are explicitly `needs_review`; all-uncertain input makes zero provider calls.
The operation lifecycle may complete while its business outcome needs review;
that is not successful technical assessment. UI distinguishes deterministic
review from model interpretation. No saved failed operation was converted into
a completed result or retried by this change.

**Verification:** read-only execution on the actual restored four-turn capture
returned a validated review outcome, four not-assessed dimensions, zero provider
calls, one uncertain pair, one versioned technical reference and Python coverage
`not_evidenced`. 61 focused backend tests including real disposable PostgreSQL
passed; one additional mixed-pair regression then passed with the focused
workflow suite. 185 frontend tests, TypeScript, production build and compilation
passed. Existing LiveKit bundle-size warning remains. No new live inference,
media playback, capture, demo data change or migration occurred.

**Acceptance: PARTIAL.** F4 live saved capture and safe non-assessable F5 handling
are verified. A grounded technical evaluation of adequate, confidently paired
interview evidence has mocked coverage but has not passed live on this fragmented
capture. Human transcript review or better future source evidence remains needed;
no transcript editing or further inference is authorized by this diagnosis.

## Closure checkpoint: actual review outcome and next speech fixture

**Live-browser verified:** recruiter UI displayed completed processing with
`needs_review`, all four dimensions not assessed, Python not evidenced, original
uncertain pair and source references. The deterministic operation was attempt 5
of the preserved operation; the prior failed attempt was backed up first. External
inference was explicitly disabled in this runtime and no provider call occurred.
PostgreSQL result survived a backend restart and authenticated status GET. The
original four transcript turns remained unchanged. A verified private custom
archive preserves this completed review result and earlier source records.

**Privacy tests:** seven real disposable PostgreSQL tests passed, including a new
review-result test for zero provider calls, independent-manager retrieval,
withdrawal, verified deletion and denial after deletion. Original evidence was
not withdrawn/deleted to demonstrate this; only separate test fixtures were used.
An initial new-test run found missing test imports; those were corrected before
the final successful run. No application privacy checks were bypassed.

**Prepared, not live verified:** a separate new synthetic 60-minute interview and
private invitation, with local generated speech fixtures. Whole-file local tiny.en
preflight recognized “Explain Python lists.” and “Python lists are mutable ordered
sequences. You can append an item to a list.” accurately; total audio 8.35 seconds.
PCM was decoded locally for this preflight, as in the existing worker. It is not
proof of browser streaming recognition, confident saved pairing or grounded Groq
analysis. Invitation preparation initially stopped under review-only runtime;
the one already-created booking was recovered without creating a duplicate.
No new transcript/caption consent has been accepted, speech played in browser or
Groq call made for this separate fixture. Synthetic saved eligibility is a setup
fixture, not an actual CV-screening claim. Await manual browser sign-in and consent.

Verdict remains PARTIAL pending any separate confident live evaluation. Existing
capture, review result and failed-attempt backups must be preserved.

## Caption startup defect — confirmed diagnosis

The recovery backend is launched from the worktree root. LocalWhisper spawned
`python -m app.integrations.stt.local_whisper_worker` without an explicit working
directory. In-process sys.path setup is not inherited by Python subprocesses.
Reproduction from that directory returned worker exit 1 and module-not-found for
app. The ready pipe reached EOF and start() raised JSONDecodeError; approve()
caught startup failure and stopped the caption session before browser audio
initialization. This is a demonstrated worker-startup defect, not a requirement
to click both consent buttons within five seconds.

Fix: resolve the model path and launch the worker with the backend directory
computed from its installed source path. No consent, authorization, inference or
STT settings changed. Regression verifies launch root independent of server cwd.
46 focused caption/finalization tests passed. Additionally two REAL local tiny.en
workers started from worktree-root launch context, reached active only after
separate participant approvals, and shut down without receiving audio frames.

Browser currently confirmed LiveKit connected with one remote participant,
generated-media mode, both storage consents and stopped captions. Read-only DB
confirmed no revocation, active/pending capture, two consents and zero turns.
Earlier WebSocket close code/reason and exception were not retained by the
existing generic close path, so exact historical socket status is unavailable;
this diagnosis does not invent it. Browser audio initialization was not verified
because activation never reached that stage. No media playback or Groq request.
A private verified archive preserves this pending state and earlier evidence.

The running backend still has the old imported launcher class. Applying the fix
requires a coordinated backend restart; pending consent receipts also live in
RAM, so do not restart then silently assume those receipts survive. Preserve and
reconcile current pending capture with the existing supported consent lifecycle
before a further browser activation. Do not create another interview or delete
pending evidence merely to hide this state. A final browser activation remains
necessary to verify client worklet initialization; it is not needed to reproduce
or validate the confirmed subprocess-import fix. Overall milestone PARTIAL.

## Coordinated restart after f284ffe

Archived the complete disposable database before restart and verified its catalog.
Read-only status already reported the empty pre-restart capture interrupted/failed
through normal stale cleanup, with no withdrawal or deletion. Capture identity,
consent timestamps/version and older evidence remain stored; nothing was reset.

Restarted only isolated backend 8024 with its working directory set to backend;
corrected LocalWhisper also pins worker cwd independently. Database 54403,
frontend 5190 and LiveKit were preserved. Authenticated login/storage GET succeeded
after restart. LiveKit server was reachable and reported one participant at the
check; two current connections are not claimed. External inference remains
explicitly blocked in this rehearsal launcher; Gmail remains disabled.

Durable consent timestamps/version are historical evidence, not reconstructible
signed receipts. Signing secret, receipts, coordinator association and temporary
caption approvals were memory-only. Both participants must therefore accept a
fresh normal storage handshake in this SAME interview; do not fabricate receipts,
clear revocation, rebook or reclaim the invitation. Existing participant-session
cookies continue to authorize normal access subject to their expiry/window.

47 caption/finalization tests passed with no skips. New opt-in real-model route
test uses the actual ASGI caption endpoints and two actual local Faster-Whisper
subprocesses, verifies no worker before both consents, active event on both
sockets and orderly shutdown without audio. Test participant authorization is
synthetic/mocked; real recruiter login was checked separately against the running
restarted backend. First test iteration raced asynchronous cleanup; final test
waits for both stopped messages and socket closes before asserting cleanup.
No new transcript, interview, media playback or provider request was made.

Browser resumption is limited to refreshing existing tabs to clear stale in-memory
UI, rejoining the SAME interview in generated mode, and both participants accepting
fresh storage then caption consent. Saved source and prior failed captures must
remain untouched. Overall PARTIAL pending actual corrected browser capture.

## Clear-speech capture ready for final F5 authorization

Actual PostgreSQL evidence: new completed/saved drained capture has three turns,
one recruiter and two candidate. It produces one answered Q&A, Python partial
coverage and one official-documentation-summary Python-list reference. Original
recognized text and speaker identities remain unchanged. Authenticated input
preparation verifies the selected capture identity against a private saved target.
A verified private archive preserves both this capture and older empty failure.

Fixed an input-selection defect: empty terminal interrupted/failed attempts no
longer invalidate a later saved capture. They are retained in PostgreSQL and
explicitly disclosed in the result warning. Incomplete attempts containing ANY
recognized text remain rejected; active or contradictory captures remain blocked.
No selection of arbitrary partial text, consent bypass or completeness claim is
introduced. Regression covers valid saved plus empty failed history and rejection
when the failed attempt contains a turn.

Isolated backend restarted with this selection fix and the final synthetic job
allowlisted. Groq is available only through the separate explicit UI disclosure
flow. No provider request was sent during preparation. Saved-transcript analysis
requires no media reconnection. Final live evaluation remains pending user click;
overall verdict is still PARTIAL until its actual outcome is inspected.

Validation for this selection fix: 67 focused backend tests passed with real
PostgreSQL enabled, no skips. Earlier offline selection/Q&A/reference suite also
passed 73 tests with six optional PG tests skipped; the subsequent PG-enabled
run exercised those database checks. No live inference was part of tests.

## Final analysis UI state recovery

Authoritative check found zero analysis records for the final interview, while
browser retained a locally generated operation ID, checked disclosure and disabled
Analyze control. Retained ID was polled despite no durable operation. Earlier
original POST response was not captured, so its exact status is not asserted.
Authenticated storage status currently returns HTTP 200, completed/saved, no
withdrawal/expiry; source preparation still yields three original turns, one
answered pair, Python partial and one official reference. Storage-unavailable
message was stale UI, not proof that the saved transcript disappeared.

Fixed frontend classification of definitive start rejections (400/401/403/404/
409/422): clear rejected local ID, uncheck disclosure and require a new explicit
user action. Network/5xx/uncertain delivery retains the ID and never automatically
retries. GET failure now includes the safe HTTP status without private details.
Reopening the same interview through ordinary navigation cleared the existing
stale component state; fresh browser storage GET visibly confirmed saved state.
No media reconnection, consent recreation, interview creation or analysis POST
was performed during this recovery.

187 frontend tests passed, including actual component rejected-start recovery
and API distinction between rejection and network uncertainty; TypeScript and
production build passed. Existing bundle-size warning remains. No Groq call.
Ready for one explicit user-authorized Analyze click; live F5 result is pending.
