# Milestone 3 interview analysis

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
