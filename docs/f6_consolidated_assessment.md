# F6 consolidated candidate assessment — Increments 1 and 2

Implemented on `feature/f6-consolidated-report`, based on verified M3
`2967ae9ef36748d33a5b3107d0122a70d8418979`. This is **not full F6 completion**.

## Evidence and scope

The official BID Section 5.4.1 F6 was not found in the inspected home files.
Scope follows the owner's Increment 1 request and existing F5/closure notes.
Increment 1 left printing/export, comparisons, complete evidence coverage and any
approved overall suitability formulation unfinished. Increment 2 below adds native
browser printing/Save as PDF; the other areas remain unfinished. No numeric combined
score, candidate recommendation, new assessment, schema migration or external
service is introduced. Reviewed M3, notifications, LinkedIn and intake are not
merged or modified by this branch.

## Verified identity and data flow

There is no canonical person/candidate table linking applications across jobs.
The supported unit is **one application**, identified by exact
`(job_id, batch_id, upload_id)`, never candidate name or email.

1. Recruiter session authentication and owned-job lookup precede candidate lookup.
2. A saved `CandidateScoreRecord` is selected by exact application, current criteria
   revision and `f2-coverage-v1`. Its payload/identity/score/weights are validated.
3. If an `InterviewSchedule` exists for that exact application, use its immutable
   `screening_snapshot` instead. Interview creation already validates saved eligible
   selection. Its job reference, upload identity, scoring version and eligibility
   are checked again. The report labels this selection-time F2 evidence and its
   revision; later F2 reruns are not silently substituted.
4. The schedule links to persisted `InterviewAnalysis` by interview, owned job,
   recruiter, criteria revision and the freshly recomputed source fingerprint.
   No analysis operation UUID is guessed from a name or arbitrary latest row.
5. Source loading reuses `PostInterviewInputService.load`: active recruiter,
   interview ownership, current confirmed revision, retention, both-party consent,
   consent version, completed captures, sample/turn completeness and source identity.
6. Saved pairs, quotations, rubric dimensions and technical citations are validated
   against that source. Deterministic coverage is recomputed only to verify the
   saved mappings match; no new interpretation or model inference is performed.
   Unvalidated saved strengths/prose are not copied. The UI displays original
   dimension justifications/evidence and original requirement follow-ups.
7. If more than one completed model/corpus variant matches, return `ambiguous`;
   this increment does not silently choose one.

An interview can survive replacement/removal of the mutable score row because it
retains a valid F2 selection snapshot. This is tested. A truly CV-less interview
is not supported by the existing selection contract: an invalid/missing snapshot
returns a safe 409, rather than inventing an interview-only candidate join.

## API and UI

Authenticated recruiter-only GET:

```text
/api/v1/jobs/{job_id}/batches/{batch_id}/candidates/{upload_id}/assessment
```

Response has a typed `f6-increment-1` contract, original F2 score/dimensions,
selection provenance, F5 availability, and validated F5 evidence when authorized.
No report record is stored. Reads take job/interview locks to serialize with
revision changes and transcript withdrawal. They perform no INSERT/UPDATE/DELETE,
lease expiration writes, retries or inference. Expired running leases are shown as
unavailable, without modifying the analysis operation.

Saved candidate cards and saved interview rows offer **View consolidated
assessment**. Excluded/unscored candidates can open reports; this does not select
them for interview. Source quotations and requirement references open the source
turn section and scroll to timestamped turns without changing workspace navigation.
F2 page/block references remain explicit. The report includes human-review and
missing-evidence warnings. It has no Analyze/Retry/Publish/Send action.

The UI fetches only on explicit request, uses `cache: no-store`, validates returned
application identities, aborts stale requests, and never persists report text in
browser storage. Close, context changes, workspace navigation and document hiding
clear it. Available interview reports are cleared at the retention deadline.
Reopening performs a fresh authenticated read. Already delivered screenshots or
external copies cannot be retroactively revoked. Increment 2 adds the explicitly
controlled browser printing workflow documented below.

## Availability and privacy

Explicit states: available, not_scheduled, disabled, withdrawn, expired, deleted,
stale, missing_analysis, pending, unavailable, ambiguous. Non-available responses
contain no interview text, rubric output, quotations or technical references.
A privacy fence is checked before querying derived analysis data. Pending/failed
physical deletion also fails closed. Withdrawn/expired/deleted interview evidence
never becomes a zero score or negative candidate conclusion; CV evidence has its
separate existing lifecycle.

Candidate invitation/privacy cookies cannot authenticate the report. Foreign jobs
and unknown application identities return generic errors. API middleware supplies
`Cache-Control: no-store`; SQL/provider details are never copied to error responses.
The synthetic home configuration still disables transcript access, inference and
email. F6 honors `TRANSCRIPT_STORAGE_ENABLED`; it does not require enabling Groq or
construct an evaluation manager merely to read an authorized persisted report.
Production activation remains outside this increment.

## Executed tests — 17 October 2026

From `/home/shafi/Projects/TalentTrace-AI/backend`:

```bash
F6_HOME_PG_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 .venv/bin/python -m pytest tests/test_consolidated_assessment.py \
 tests/test_candidate_scoring.py tests/test_score_integration.py \
 tests/test_saved_score_discovery.py tests/test_evaluation_input.py \
 tests/test_interview_evaluation.py tests/test_interview_analysis_api.py \
 tests/test_durable_analysis.py -q
```

Result: **97 passed, 20 skipped**, no failures. F6 contributes **22 passing
checks**, including **17 executed PostgreSQL cases**. These cover complete/CV-only
and selection-snapshot-only evidence, missing/pending/failed/ambiguous analysis,
withdrawal, expiry, deletion, disabled access, criteria/source changes, unsupported
consent, tampering, anonymous/candidate/foreign access, invalid application and
invalid snapshot; repeated responses are stable and SQL write statements absent.
Manager/workflow invocation traps verify report GET does not start inference.

F6 database cases opt in explicitly, check the exact synthetic home database
address/name, create random fixture identities under an outer transaction, and
roll everything back. No migrations, image pulls, database recreation or existing
records are needed. Unit-only invocation without the gate skips these 17 cases.
The 20 regression skips retain their existing office-container-dependent
`TRANSCRIPT_PG_TEST` fixture. This is **not full database acceptance**, and does not
claim concurrency/withdrawal-race verification for the new report on separate
connections. The existing parent-lock privacy protocol is reused.

Frontend: `pnpm test` — **194 passed**, no failures/skips (7 new report checks).
`pnpm build` — TypeScript and Vite passed; existing LiveKit >500 kB chunk warning.
Final commands and results were rerun after implementation repairs. Early runs
exposed test-fixture event-loop and PostgreSQL constraint assumptions; those
fixtures were corrected rather than relaxing production constraints.

## Beginner walkthrough

1. Open the running local frontend and sign in with the existing synthetic account.
2. Select **Synthetic F6 report fixture**. It contains one explicitly synthetic
   CV-only saved score, added for this walkthrough; no interview/evaluation exists.
3. In Candidate Screening, expand/load **Previously saved candidate scores**.
4. Click **View consolidated assessment**. Inspect the saved CV coverage/breakdown
   and its page/block evidence. The interview section honestly says not scheduled.
5. Close/reopen to fetch afresh. You can also open reports from saved interviews.
   Available F5 rendering is covered with synthetic fixtures in automated tests;
   no live interview or model call was repeated for this walkthrough.

No dependencies/models were installed for F6. The preserved F2 environment and old
Docker volume remain unchanged. The local backend was restarted to serve the new
route; synthetic feature flags were not enabled.

## Recommended next small step

Review the official BID F6 text, then add approved-criterion descriptions and
explicit per-requirement missing-CV evidence rows for unscored candidates. Existing
F2 persistence omits dimension evidence when unscored; do not fabricate that data.
Design the smallest persisted evidence extension before claiming full coverage.
Explicit saved model/corpus selection can follow. Browser printing is now
implemented in Increment 2; further export formats and comparison need review, and no overall number should be added
without an approved formulation.

## BJIT viva questions

1. **How do you know F2 and F5 belong to the same candidate?**
   Exact job/batch/upload identity links the immutable selection snapshot to its
   scheduled interview; owned interview/revision/fingerprint links F5 to source.
   This is an application identity, not a person-matching claim.
2. **Why is there no combined score?**
   F2 is weighted CV requirement coverage; F5 has advisory rubric dimensions.
   Combining them would need an approved scoring design, absent in this increment.
3. **What happens after transcript withdrawal or expiry?**
   The interview privacy fence denies F5 text even before cleanup completes.
   The next report read returns an explicit restricted state; missing evidence is
   never presented as poor performance, and existing cleanup removes derived data.

## Changed files

- `backend/app/api/router.py`: register the report router.
- `backend/app/api/routers/consolidated_assessment.py`: authenticated GET and safe storage errors.
- `backend/app/schemas/consolidated_assessment.py`: typed report and availability contract.
- `backend/app/services/consolidated_assessment.py`: identity join and evidence/privacy validation.
- `backend/tests/test_consolidated_assessment.py`: synthetic unit and rollback-only database tests.
- `frontend/src/api/consolidatedAssessment.ts`: GET and identity/response validation.
- `frontend/src/api/savedScoreValidation.ts`: existing score validator moved out of UI to avoid a circular dependency; legacy export retained.
- `frontend/src/components/ConsolidatedAssessment.ts`: explicit-load report, evidence links and memory lifecycle.
- `frontend/src/components/SavedScores.ts`: report entry point and validator re-export.
- `frontend/src/components/InterviewScheduling.ts`: report entry point on saved interviews.
- `frontend/tests/consolidatedAssessment.test.ts`: report rendering, validation, GET and failure tests.
- `docs/f6_consolidated_assessment.md`: implementation, privacy, limitations and execution record.
- `README.md`: documentation link.

Browser walkthrough passed for the CV-only fixture, including expanded F2
breakdown and page reference. Screenshot is ignored local evidence at
`data/home/f6-report-verified.png`. The existing app was left running on localhost.

## F6 Increment 2 — native printable report (17 October 2026)

Implemented on `feature/f6-report-export` from committed Increment 1
`1f77c3062435abab7f12bfb9c938094ab6ee6901`; parent branch is preserved.
This is incremental F6 work, not full F6 completion. The API contract remains
`f6-increment-1`: printing presents saved evidence without changing its meaning.
The original BID file still was not available locally; printable/report scope
follows the owner's explicit F6 requirement for this increment.

### Workflow and actual behavior

1. Sign in, open a saved candidate's consolidated assessment, and click
   **Print / Save as PDF**. Merely opening/navigating the report never prints.
2. The action performs a fresh, uncached authenticated GET to the existing report
   endpoint, clearing the older on-screen evidence first. A failed/aborted/expired
   response never opens printing. A fresh
   withdrawn response includes only its restricted state and remaining CV evidence;
   it does not reuse the previously displayed interview text.
3. A temporary direct-child-of-body React portal holds only that fresh report.
   Every `details` element in this copy is explicitly opened before `window.print()`.
   This includes the existing F2 score disclosure, CV references, saved technical
   references and timestamped transcript evidence. The screen's disclosure state
   is not changed. Print styles isolate that copy and hide navigation, buttons,
   dashboard content, other candidates and hidden workspace pages.
4. The browser owns its native dialog: select a printer or **Save as PDF**, review
   page size/margins/headers/footers, then print/save or cancel there. No automatic
   file, destination, download or server-side PDF is created.
5. `afterprint` removes the in-memory copy and listeners, including on normal dialog
   cancellation. Context change/unmount, errors, retention expiry or a five-minute
   maximum also clear it. If a browser omits `afterprint`, **Clear prepared print
   copy** clears application memory; it cannot close a browser-owned dialog.
   Reopen the report for another fresh print. Only one report may prepare printing
   at a time, preventing duplicate print roots or a wrong-candidate snapshot.

The printable content includes job title/reference/identity, application and batch
identity, criteria revision, F2 score provenance/breakdown/source pages, authorized
F5 rubric/coverage/strengths/follow-ups, technical references, original timestamped
turns, availability/limitations and recruiter-review notices. Full source-turn
identifiers accompany quotations on paper; matching IDs accompany source turns.
A UTC **Print view prepared** timestamp records retrieval/preparation context;
it is explicitly not an evaluation timestamp or proof that printing completed.

Print CSS supplies paper margins, black text on white, readable type, wrapping
for long UUIDs/text/URLs, headings kept with following content, normal multi-page
flow, paragraph widow/orphan rules and repeating table headings where tables
exist. There are no new tables or artificial score formulas. Browser engine and
paper settings still determine exact pagination. Using the browser's general
Print shortcut without a prepared report produces an instruction rather than
printing the recruiter dashboard.

### Privacy and implementation choice

No new endpoint, inference, migration, dependency, storage or assessment mutation
was added. Existing authorization/consent/ownership/revision/retention checks are
reused on the fresh GET. Source evidence is validated as in Increment 1; restricted
states contain no interview text. An additional retention check runs immediately
before native printing. The preparation is not saved to localStorage, sessionStorage,
IndexedDB, a Blob URL, an HTML download or a new browser window.

Native print dialogs can trigger document visibility changes. Screen evidence is
still cleared on hiding; an already prepared print copy is retained only for its
bounded print lifecycle so the native dialog does not erase its own document.
Hiding before preparation aborts the request. The copy is hidden synchronously
before cleanup if its authorization context expires/changes. Server revocation
cannot retract an already delivered browser snapshot, open print preview, PDF,
spool file or paper copy. The report warns that copies are confidential and outside
application retention; the recruiter controls their secure storage and disposal.
There is no claim of revocation or physical deletion of externally saved copies.

Native printing reuses the existing browser layout, fonts and printer/PDF dialog.
It avoids a second rendering engine, extra dependencies, server-side sensitive
files, download endpoints and additional operational/storage costs. Automated PDF
export, encryption, signing and cross-browser identical pagination are not provided.

### Increment 2 verification

Executed:

```bash
cd /home/shafi/Projects/TalentTrace-AI/frontend
pnpm test
pnpm build
cd /home/shafi/Projects/TalentTrace-AI/backend
F6_HOME_PG_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .venv/bin/python -m pytest tests/test_consolidated_assessment.py -q
```

- Frontend: **203 passed**, zero failures/skips. Nine additional tests cover fresh
  explicit printing, no print on denied/aborted/expired reads, cleanup/cancellation
  hooks, retention recheck, concurrent print rejection, print isolation/expansion,
  complete F5 content/source identities, long escaped synthetic text and
  CV-only/missing/withdrawn/expired/deleted
  content. Existing report availability tests remain in the suite.
- TypeScript and production Vite build passed. Existing LiveKit >500 kB chunk warning
  remains unchanged in nature.
- Focused backend: **22 passed**, zero failures/skips, including **17 PostgreSQL
  cases** in rollback-only synthetic transactions. No backend implementation changed.
  The older office-dependent gates were not run; full DB acceptance is not claimed.
- In-app browser: synthetic report and explicit print button loaded; clicking it
  entered the native-print lifecycle. The native preview was not accessible in the
  UI; Escape returned the app to its normal state after the print attempt. Physical
  printing, actual Save as PDF, printed page layout and automatic native-dialog
  cancellation cleanup remain unverified in this embedded browser. Unit tests exercise
  lifecycle callbacks; markup/CSS tests do not prove actual browser pagination.
- No external AI calls, models, framework installs or database migrations.

Changed files for Increment 2: `frontend/src/api/assessmentPrinting.ts`,
`frontend/src/components/ConsolidatedAssessment.ts`, `frontend/src/index.css`,
`frontend/tests/assessmentPrinting.test.ts`,
`frontend/tests/consolidatedAssessment.test.ts`, and this document.

Remaining F6 work includes comparison, complete persisted requirement evidence,
explicit saved analysis-version selection, and any approved overall suitability
formulation. Additional export formats and production privacy/disclosure acceptance
are separate work. A small follow-up should verify this native print flow in the
user's normal desktop browser with synthetic long multi-page evidence before
claiming print-layout acceptance across browsers.
