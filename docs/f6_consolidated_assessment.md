# F6 consolidated candidate assessment — Increments 1–5B

Implemented on `feature/f6-consolidated-report`, based on verified M3
`2967ae9ef36748d33a5b3107d0122a70d8418979`. This is **not full F6 completion**.

## Evidence and scope

The official BID Section 5.4.1 F6 was not found in the inspected home files.
Scope follows the owner's Increment 1 request and existing F5/closure notes.
Increment 1 left printing/export, comparisons, complete evidence coverage and any
approved overall suitability formulation unfinished. Increment 2 below adds native
browser printing/Save as PDF. Increment 3 below adds two-application comparison;
complete coverage and an approved overall formulation remain unfinished. No numeric combined
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

## F6 Increment 3 — same-job candidate comparison (17 October 2026)

Implemented on `feature/f6-candidate-comparison`, based on Increment 2
`c49b2578cfc11d26610193ba0d8d9da2113ff761`. Parent increments and verified M3 are
preserved. This increment does not claim full F6 acceptance. The official BID
PDF was still not present in the inspected Downloads/Documents paths; comparison
scope follows the owner's explicit mandatory F6 request, not an independently
reverified BID quotation.

### Architecture and actual data flow

The recruiter loads **Previously saved candidate scores**, selects **Application A**
and **Application B**, then explicitly clicks **Compare selected applications**.
Choices come from the selected job's existing current saved-score discovery.
The exact identity remains `(job_id, batch_id, upload_id)`, not a name, CV filename,
email address or inferred person identity. Duplicate exact application selections
are blocked in UI, client API validation and backend validation. A repeated upload
UUID in another batch is a different application identity; there is no new
cross-application person deduplication claim.

One authenticated, uncached GET is used:

```text
/api/v1/jobs/{job_id}/assessment-comparison
  ?left_batch={uuid}&left_upload={uuid}&right_batch={uuid}&right_upload={uuid}
```

The backend obtains the owned job lock, checks confirmed criteria, and calls the
existing `consolidated_assessment` service for each exact application using the
same session/transaction. No second implementation of F2/F5 evidence generation
or source/privacy validation is introduced. Job locking stabilizes revision and
weights across both reads; existing interview locks serialize with withdrawal.
A failed second lookup returns a generic error, not a partial first report.
Both reports must use the current criteria revision and current scoring weights;
historical/incompatible selection snapshots are rejected with 409. Selection-time
F2 snapshots remain the evidence source where an interview exists; later F2 reruns
are not silently substituted. Final retention checking redacts an interview if
its deadline passes while the other report is retrieved.

The typed `f6-comparison-1` response contains the two existing typed report
contracts in the original A/B order, job identity, criteria revision and a review
notice. It performs no score arithmetic, cross-interview rubric aggregation,
ranking, tie-breaking, selection recommendation, writes or inference. F2 numbers
remain weighted CV requirement coverage, not a new overall suitability score.
Different interviews can cover different questions; the UI says so explicitly.

### Presentation and privacy

A summary table aligns application/batch identities, criteria revision, original
F2 score, screening status, skill/experience/education component values and
interview availability. Missing scores remain **Not scored**, not zero.
The detailed A/B columns reuse `AssessmentView`, including original F5 dimensions,
coverage/gaps, strengths/follow-ups, technical citations and source-turn links.
No arbitrary result is chosen when multiple valid analysis variants exist: the
existing `ambiguous` state is retained. A future selection policy should require
an explicit authorized operation/model/corpus choice, validate it against the same
current source and disclose those versions for each candidate.

Wide layouts use two columns; below 1000 px the detailed reports and selectors
stack. The summary remains paired with wrapping identities. No independent scroll
panes or fixed report heights are introduced. The current narrow embedded browser
was verified with this stacked layout and side-by-side summary.

Each comparison retrieval rechecks recruiter authentication and ownership for both
applications, along with the inherited consent, retention, deletion, revocation,
criteria and transcript fingerprint checks. Candidate-facing capabilities cannot
read it. Restricted evidence has no interview text/assessment. Source quote links
remain scoped to their rendered report instance. The client validates exact A/B
identities, response order/revision/weights and the existing report contracts.

Changing selections, job/revision, reloading the saved choices, navigating, hiding
the document or closing clears comparison evidence and aborts pending retrieval.
Sequence guards discard stale responses. The earliest available interview
retention deadline clears the whole comparison. Recompare performs a fresh GET;
no automatic fetch, polling, browser storage, print or external action is added.
Like prior reports, previously delivered browser content cannot be retroactively
revoked by a later server withdrawal; reopening/retrieving checks it again.

### Test evidence

Executed on the existing synthetic home PostgreSQL database:

```bash
cd /home/shafi/Projects/TalentTrace-AI/backend
F6_HOME_PG_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 .venv/bin/python -m pytest tests/test_consolidated_assessment.py \
 tests/test_candidate_comparison.py -q
cd /home/shafi/Projects/TalentTrace-AI/frontend
pnpm test
pnpm build
```

- Backend: **41 passed, 0 failed, 0 skipped**. This includes **19 new PostgreSQL
  comparison cases**, plus Increment 1's 22 checks (17 PostgreSQL). Total executed
  PostgreSQL cases: **36**. Random fixtures and edits are rolled back; the helper
  verifies its synthetic recruiter is absent afterward. No existing records,
  tables, migrations, images or database services are recreated.
- Tests exercise two valid same-job applications, CV-only versus available F5,
  missing/withdrawn/expired/deleted/changed/ambiguous interview sources, duplicate,
  different-job and foreign application selections, foreign recruiter/anonymous/
  candidate access, wrong batch, unconfirmed/stale criteria, incompatible weights,
  and expiry during pair retrieval. Repeated GET results are stable; SQL write
  statements are absent, and existing manager/workflow traps disallow inference.
- Frontend: **211 passed, 0 failed, 0 skipped**, including 8 new comparison checks:
  exact identity validation, wrong-order/revision/weight/protected-text rejection,
  CV-only/F5 rendering, unavailable/ambiguous states, fresh credentialed GETs,
  generic errors/no request on invalid selection, explicit-selection empty state,
  and responsive/memory lifecycle structure.
- TypeScript and Vite production build passed; existing LiveKit >500 kB chunk
  warning remains. Static CSS/lifecycle assertions do not establish every browser
  viewport, async timing race or physical print behavior.
- Browser: synthetic scored and explicitly unscored applications loaded; comparison
  summary and detailed states rendered. Selecting the same application in both
  selectors immediately cleared the old result and disabled comparison. Restoring
  distinct choices and retrieving again produced the same persisted values.
  Screenshot: ignored local `data/home/f6-comparison-verified.png`.
- The persistent walkthrough adds one clearly synthetic unscored score record
  under the existing synthetic F6 fixture job; prior data is unchanged. No mock
  interview result was persisted for the walkthrough. Complete F5 comparisons use
  rollback-only test fixtures, not real candidates, audio or inference.
- Older office-container-dependent PostgreSQL gates were not enabled/rerun;
  these results do not claim full database, concurrency or full F6 acceptance.

### Print cancellation review — separate follow-up

Increment 2's print code was reviewed without modification. It registers
`afterprint`, removes temporary DOM/listeners, has context/retention/five-minute
cleanup, explicit manual clearing and a single-print guard. Unit tests cover those
hooks, but native cancel/Escape delivery of `afterprint` remains unverified on the
intended desktop browsers. The embedded browser attempt was not an adequate proof.
This needs a **separate compatibility/cleanup follow-up**: reproduce cancel/Escape
in the user's normal browser and verify temporary DOM removal, enabled controls
and a second print. If that browser omits the event or retains state, make a narrow
cleanup fix with a regression test. Review alone found no proven new defect and
this increment does not claim the gap fixed or redesign printing.

### Changed files, limitations and next step

- `backend/app/schemas/consolidated_assessment.py`: comparison response contract.
- `backend/app/services/consolidated_assessment.py`: paired existing report reads and current revision/weight checks.
- `backend/app/api/routers/consolidated_assessment.py`: authenticated comparison GET.
- `backend/tests/test_candidate_comparison.py`: rollback-only PostgreSQL coverage.
- `frontend/src/api/candidateComparison.ts`: exact selection and response checks.
- `frontend/src/components/CandidateComparison.ts`: selectors, summary and reused reports.
- `frontend/src/components/SavedScores.ts`: comparison entry point.
- `frontend/src/index.css`: responsive comparison layout.
- `frontend/tests/candidateComparison.test.ts`: focused client/rendering checks.
- `docs/f6_consolidated_assessment.md`: this implementation and verification record.

Selection discovery currently includes current saved F2 rows; applications whose
only remaining evidence is an interview selection snapshot are supported by the
underlying report reader but are not listed in these selectors. Cross-job,
historical-criteria, more-than-two and cross-person matching comparisons are not
supported. F5 dimensions/questions are shown as recorded, without forcing unlike
interviews into one normalized score. Comparison printing/export is not added.

Remaining F6 work: complete persisted per-requirement evidence for unscored
applications, explicit analysis-version selection, broader export/print acceptance,
and any separately approved overall suitability formulation. The next small step
is the native print-cancel validation above, followed by a scoped design for the
missing persisted CV-evidence coverage. No dependency or model download was needed.

### Three viva questions

1. **Why one comparison request?** It holds one owned job/revision context while
   both existing report readers validate their exact applications and privacy.
2. **How do you handle a withdrawn interview or ambiguous result?** Withhold its
   text, retain the explicit availability state, and require deliberate authorized
   version selection rather than inventing or arbitrarily choosing evidence.
3. **Why no combined score or winner?** F2 is CV requirement coverage and F5 is
   advisory question-specific evidence; combining them requires an approved design.

## F6 Increment 4 — persisted application discovery and snapshot consistency

Implemented 17 October 2026 on `feature/f6-evidence-completeness`, from verified
Increment 3 `9099e50072ffeffbbcc467f5bf33d8cc674e9a1d`. No migrations, inference,
score formulas, backfill, model downloads or unrelated branch integration.
The official BID PDF remains unavailable in the inspected local locations;
traceability scope follows the owner's explicit request and verified contracts.
This increment does not claim full F6 acceptance.

### Persistence audit and state distinctions

- `candidate_scores` is keyed by job/batch/upload/revision/scoring version. A valid
  scored payload retains the original requirement matches, explanations, page/block
  references and component breakdown. Its numerical/identity contract is validated.
- An unscored payload may preserve a screening decision/reason but **always has no
  dimensions** under the existing `CandidateScore` contract. The full matching
  result returned during screening is not independently persisted by `persist_scores`.
  Thus a decision is evidence that screening occurred, not recoverable complete
  requirement-level evidence. Processing failures may have no decision at all.
- `interview_schedules` has a unique job/batch/upload key and immutable selection
  snapshot. This survives mutable score replacement/deletion. A valid snapshot is
  reportable even without a score row. Its revision/weights must match current
  confirmed criteria to participate in comparison; older snapshots remain visible
  and reportable with the existing stale/restricted F5 behavior.
- Historical F2 rows without a selection snapshot are listed explicitly, including
  recorded revisions, but no arbitrary historical payload is silently substituted
  for the current report. Invalid CV artifacts have no report action.
- The local `external_cv_submissions` ledger proves a persisted application identity,
  not a profile, consent grant, score or available source file. Ledger-only entries
  are labelled unavailable; contact fields are never loaded by discovery.
- Native intake stores files on disk before screening; there is no universal durable
  application registry or application-wide withdrawn/deleted marker in these models.
  Filesystem-only, unscreened uploads are outside this bounded database listing.
  Empty listing does not mean no CV files exist. No missing application or withdrawal
  flag is invented. Foreign/missing jobs are denied, and nonexistent identities are
  not manufactured. Interview withdrawal remains separate from CV evidence lifecycle.

### Discovery behavior

Authenticated GET `/api/v1/jobs/{job_id}/assessment-applications` returns a typed,
metadata-only union of owned job score rows (including historical revisions), owned
interview selection identities and local ledger identities. Deduplication and sort
use exact `(job_id, batch_id, upload_id)`. It does not query F5 analysis/transcript
text, access another intake database, scan files, parse CVs or call models.

Existing CV association/eligibility checks were extracted into `persisted_cv` and
are shared by discovery and the unchanged report policy. Each discovered identity
has an explicit state/label, detail, recorded revisions, evidence revision, report
availability and comparison availability:

| Label | Meaning |
| --- | --- |
| Scored | Valid current F2 score and original component evidence |
| Screening evidence available; not scored | Persisted decision/reason; missing requirement breakdown disclosed |
| Historical selection snapshot | Preserved selection-time CV evidence, with its actual revision |
| Evidence unavailable or restricted | Ledger-only, historical-only, failed processing or invalid CV evidence; reason disclosed safely |

“Historical selection snapshot” denotes provenance, even when its revision remains
current. Invalid snapshots do not fall back to a different mutable score silently.
Interview consent/withdrawal/retention are revalidated only through the existing
report boundary; metadata and enabled buttons are not authorization capabilities.

Discovery is capped at 200 distinct identities and 500 score-history rows. Exceeding
a bound returns 409 with no partial list. Pagination is future work. Only IDs,
revision metadata and fixed explanations are returned, never emails, raw payloads
or private exception details.

The new **Load application evidence** action is independent of **Load saved scores**:
missing/invalid current score batches no longer hide discovery. Valid evidence
cards reuse the report/print component. Comparison selectors now consume the
current-compatible discovered identities, including snapshot-only applications.
Selections remain explicit; job/revision changes and refresh discard old data and
abort stale requests. No persistent browser storage or automatic inference is used.
Existing report/print privacy lifecycles remain intact; discovery metadata does not
clear the parent during native print visibility events and erase its print copy.

### Transaction consistency audit and correction

The running database reports `default_transaction_isolation = read committed`.
The engine previously specified no isolation override. Increment 3's job lock
stabilizes criteria/weights; existing interview locks protect each interview after
its lock is obtained. They **do not produce a common MVCC snapshot**: a conforming
F5 worker can lock interview B and commit its analysis while the request is still
reading A. One transaction alone was not sufficient evidence of snapshot consistency.

The smallest correction is request-scoped **REPEATABLE READ** for discovery and
comparison. `snapshot_session` acquires the connection with this isolation setting
before `current_recruiter` executes its authentication SELECT. FastAPI's cached
`database_session` supplies the same session to both dependencies. Subsequent
report/source reads see that transaction's snapshot. Single-report/print endpoints
and the engine/database default remain unchanged. There are no new locks or global
serialization; discovery itself is an unlocked snapshot read, and comparison keeps
only its existing owned-job/interview locks.

Privacy fences are retained. If interview B's withdrawal changes its parent row
after the snapshot begins but before the request locks it, PostgreSQL raises a
serialization failure; the endpoint returns a generic 503 with no partial A/B
report text. The client must explicitly retrieve again. No automatic retry or
inference occurs. A fresh request sees the new result/withdrawal. Clock-based
retention checks still run, including the existing final pair deadline guard.

A snapshot is current as of this request's first query, not continuously live.
Parent-fenced privacy writers follow the existing protocol. Direct maintenance
SQL that edits/deletes sensitive child rows without the required parent privacy
fence is not newly supported. Already delivered content cannot be revoked.

### Verification — executed checks

```bash
cd /home/shafi/Projects/TalentTrace-AI/backend
F6_HOME_PG_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 .venv/bin/python -m pytest tests/test_consolidated_assessment.py \
 tests/test_candidate_comparison.py tests/test_assessment_discovery.py \
 tests/test_comparison_snapshot.py -q
cd /home/shafi/Projects/TalentTrace-AI/frontend
pnpm test
pnpm build
```

- Backend: **59 passed, 0 failed, 0 skipped** in the final run: 5 unit checks and
  **54 executed PostgreSQL cases**, including 15 new discovery checks and 3 new
  independent-connection isolation/privacy cases.
- Discovery checks cover scored/unscored/failed, snapshot-only/current and historical,
  old F2-only history, invalid snapshots, missing records, ledger-only/deduplicated
  identities, foreign/different jobs, unauthorized/candidate access, explicit limits,
  withdrawn interview exclusion from reports and read-only stable retrieval.
- Real concurrency tests use two distinct `pg_backend_pid()` values. A deterministic
  writer commits B's F5 analysis between A and B reads. READ COMMITTED control returns
  mixed states; production REPEATABLE READ returns both original states. Reload sees
  the committed result. A concurrent parent withdrawal produces safe 503, followed
  by a fresh report showing B withdrawn with no B text.
- Existing rollback fixtures explicitly share one bound session for authentication
  and snapshot dependencies. Independent-connection tests use the production
  dependency and assert `SHOW transaction_isolation = repeatable read`. Their own
  random fixture rows must be committed for another connection to see them; cleanup
  removes only those test-created identities. Existing development data is preserved.
- Frontend: **217 passed, 0 failed, 0 skipped**, including 6 new discovery checks.
  TypeScript and production build passed; existing LiveKit chunk warning remains.
- Authenticated browser smoke check used the existing synthetic F6 job against the
  running backend: discovery loaded before saved-score batches were requested,
  displayed scored/unscored labels, compared both applications, and opened the
  unscored report with its existing Print / Save as PDF action. Snapshot-only and
  concurrent-change cases were verified through PostgreSQL tests. Screenshot:
  `data/home/f6-discovery-verified.png` (ignored local artifact). The native print
  dialog was not exercised again in this increment.
- SQL write-statement assertions and manager/workflow invocation traps remain enabled
  for discovery/report reads. No scoring/evaluation is triggered by viewing.
- Initial database runs failed because Docker Desktop/PostgreSQL were stopped.
  The existing user service/container were restarted, not recreated. An early fixture
  dependency override caused overlapping savepoints and was corrected to reuse the
  same cached session. The final results above are the corrected executed runs.
- Older office-container-dependent gates were not enabled; full database and F6
  acceptance are not claimed. Native print cancellation remains a separate follow-up;
  the print implementation is unchanged.
- Free space measured about **3.4 GiB**, lower than the prior session. No dependencies,
  images, models or caches were installed/deleted by this increment.

### Missing evidence contract — proposed follow-up, not implemented

Persist a bounded, versioned original screening-result artifact independently of
whether numerical scoring succeeds. Key it by the existing job/batch/upload,
confirmed criteria revision and screening run/version; retain the reviewed criteria,
source fingerprint, parse status, original requirement matches/explanations/source
references, screening decision and failure reasons. Save it atomically with score
persistence under the existing job lock. Define CV retention/deletion and access
rules before implementation. Preserve original evidence rather than recomputing it
on report GET. Existing unscored rows cannot be backfilled from a decision alone;
any future re-screening would need a separate explicit authorized action.

No such table, migration, backfill or application registry is added now. A broader
registry with application-wide withdrawal/deletion would be a separate design.
This increment improves discoverability without claiming to restore lost evidence.

### Changed files and viva explanation

Backend: `api/routers/consolidated_assessment.py`,
`schemas/consolidated_assessment.py`, `services/consolidated_assessment.py`,
new `services/assessment_discovery.py`, rollback fixture
`tests/test_consolidated_assessment.py`, and new
`tests/test_assessment_discovery.py` / `tests/test_comparison_snapshot.py`.
Frontend: new `api/applicationDiscovery.ts`, `components/ApplicationDiscovery.ts`
and `tests/applicationDiscovery.test.ts`; updated `components/SavedScores.ts`,
`components/CandidateComparison.ts` and `tests/candidateComparison.test.ts`.
Documentation: this file.

Viva: “An application is an exact job/batch/upload identity. I union existing
persisted identities, validate their CV artifacts, and distinguish current scores,
unscored decisions and selection snapshots. I cannot reconstruct requirement
quotes that were never saved. Comparison now reads one repeatable database snapshot;
concurrent withdrawal conflicts fail closed through the existing privacy locks.”

## F6 Increment 5A — suitability evidence profile (17 October 2026)

Branch `feature/f6-suitability-evidence` starts at verified, published Increment 4
`01a277b5e1ac0620e8d633c55bfced6c16566143` in the original project directory.
No worktree, merge, migration, inference, new dependency or persisted judgment is
introduced. Earlier increment sections above retain their historical findings.

### Requirement authority and the genuine implementation gap

The owner's Increment 5A request supplies the F6 Section 5.4.1 requirements:
combine CV screening, requirement scoring and interview analysis; make the overall
position component-supported rather than an opaque number; summarize strengths,
weaknesses, gaps and verification; support print/export/comparison and traceability.
This is owner-supplied requirement text, not a newly located original BID PDF or
trainer approval of a formula. The original PDF is still not independently verified.

Existing F6 already renders F2 components, source references, authorized F5
question findings, requirement topic coverage, follow-ups and restricted states.
Duplicating that evidence or building another report endpoint was unnecessary.
The genuine gap was a concise cross-source requirement index, trustworthy plain
requirement labels for CV/unscored rows, and an explicit pending-judgment message.

### Implementation and workflow

Open any existing consolidated report. A **Suitability evidence profile** now states
**Overall suitability position: pending recruiter confirmation.** It distinguishes:

- CV score: the unchanged F2 weighted requirement coverage, or explicitly not scored.
- Interview findings: existing qualitative F5 interpretations, with unverified ASR.
- Evidence completeness: available persisted CV match and authorized Q&A counts;
  absence is described as unavailable, not a zero performance result. Counts are
  not coverage of all possible interview questions and are not an overall rating.
- Overall suitability: a recruiter-confirmed judgment, not implemented here.

A requirement index shows confirmed description and mandatory/preferred flag,
original CV match status, original interview topic status and mapped question
wording, and the existing requirement follow-up where available. Missing mappings
are marked unassessed. Literal topic mention is never promoted to competence;
absence of a literal match is not proof of missing skill. Generic verification
prompts are static UI instructions, not new candidate findings. Recorded F5 status
counts are an index into the unchanged answer-level justifications, not a score.
Supported findings remain evidence-linked strengths; `concern` is explicitly
labelled a documented concern. Partial/uncertain/not-assessed findings retain
review labels. An unavailable source generates no interview findings or questions.

CV links open the original CV evidence disclosure; question links reach the saved
answer/rubric section; existing transcript links retain exact quotations and
source timestamps. Requirement IDs sit in audit disclosures, and full application
IDs remain accessible in an audit disclosure. Native printing already expands
all disclosures, including these. No evidence is removed from the printed report.

The additive report field `confirmed_requirements` reuses `ScreeningCriterion`.
It comes from the validated `ReviewedJobSnapshot` only when the job reference and
report/job revisions match and saved CV match IDs/categories belong to that
snapshot. Otherwise it is empty. No new database query is needed: the owned job
was already loaded under the existing lock. Unscored reports may therefore list
confirmed requirements while explicitly withholding all nonexistent CV matches.
Older selection snapshots keep their original F2 evidence but cannot borrow
current names. Valid authorized F5 mappings may supply their already-validated
requirement descriptions; no protected F5 data is used in restricted states.

`SuitabilityEvidence` is a presentation component over the authorized report,
not a second business-rule/evaluation service. `AssessmentView` includes it once,
so report, direct-body print copy and both comparison columns use the same source
and interpretation. The table wraps text, scrolls horizontally if needed on narrow
screens, and permits long rows to paginate in print. The client requires bounded,
well-shaped, uniquely identified confirmed requirements. Deploy the matching
backend/frontend together; an old backend without this context is rejected by
the updated client rather than guessing requirement names.

### Privacy and consistency

Existing job/recruiter ownership, exact application identity, consent, retention,
withdrawal/deletion, revision, fingerprint and saved-analysis validation remain
unchanged. Non-available interview responses still contain no derived text.
The profile additionally gates all interview use on `state == available`; tests
also exercise stale in-memory objects with a restricted state. There is no new
record, browser storage, cache, download endpoint, background request or inference.
Comparison retains request-scoped REPEATABLE READ and existing privacy locks.
Its final expiry replacement automatically removes F5 profile material because
the profile is derived from the final returned report, not a separately cached
summary. Already delivered PDF/paper/browser snapshots cannot be revoked.

### Executed verification

```bash
cd /home/shafi/Projects/TalentTrace-AI/backend
F6_HOME_PG_TEST=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
 .venv/bin/python -m pytest tests/test_consolidated_assessment.py \
 tests/test_candidate_comparison.py tests/test_assessment_discovery.py \
 tests/test_comparison_snapshot.py -q --tb=short
cd /home/shafi/Projects/TalentTrace-AI/frontend
pnpm test
pnpm build
```

- Backend: **65 passed, 0 failed/skipped**: 11 unit checks and the existing 54
  executed PostgreSQL cases. Six new unit cases cover current/historical/unconfirmed/
  malformed/foreign/category-mismatched requirement context. Existing database cases
  now assert requirement-context consistency for authorized F5, CV-only, current
  snapshots, unscored records and old snapshots. Authorization, ambiguity, consent,
  withdrawal/deletion/expiry, SQL no-write assertions, inference traps and actual
  two-connection comparison/withdrawal cases all passed.
- Frontend: **224 passed, 0 failed/skipped**, including seven new profile checks:
  concept separation, plain labels, original components, strengths/concerns,
  unanswered requirements, all restricted states, historical context absence,
  malformed context, working evidence targets, and screen/print/comparison parity.
  TypeScript and production build passed. Existing LiveKit chunk warning remains.
- An initial TypeScript check caught a string-index typing mismatch in the topic
  label map; it was corrected before the passing checks. No production rule was
  relaxed to pass tests.
- PostgreSQL checks reuse the explicit synthetic home fixtures: rollback-only
  cases leave no rows; separate-connection cases commit only random synthetic
  records and delete their own rows afterward. Existing private records are not
  changed. Older office-container gates and a full backend regression were not run.
- No Groq, Whisper/CUDA, paid API, image/model download or schema migration ran.
  Native print-dialog cancellation and full long F5 PDF pagination remain outside
  this increment; markup parity does not prove browser pagination.
- Authenticated browser smoke check passed against the running production routes
  using the existing synthetic unscored application. The new profile displayed
  pending recruiter confirmation, null-score/missing-evidence wording and the
  unchanged print action. No new candidate fixture or analysis was saved for this
  walkthrough. Screenshot: ignored local
  `data/home/f6-suitability-evidence-verified.png`. The synthetic job's actual
  confirmed description is `skill-0`; the UI preserves it rather than inventing a
  friendlier description. Plain descriptive names are separately tested with
  synthetic Python programming / SQL transactions criteria.

### Smallest proposed 5B record — design only

One versioned recruiter-confirmation record can hold:

- UUID; exact job/batch/upload; owning recruiter; authenticated reviewer ID and UTC
  confirmation time. Never accept a client-supplied reviewer identity.
- Approved qualitative position (including insufficient basis), bounded rationale
  and evidence references (criterion IDs, CV references, F5 Q&A/dimension IDs).
  No numeric total or automatic hire/reject field.
- Criteria revision and canonical criteria/weights digest; CV source kind,
  scoring version and validated payload digest; optional F5 operation ID, transcript
  input digest, rubric/model/corpus versions and effective retention deadline.
  Null F5 explicitly means a CV-only scope, not a failed interview.
- Version counter for optimistic confirmation/update; status confirmed/stale/
  invalidated. Define the approved position vocabulary before creating a migration.

Save must revalidate all dependencies under the existing job/interview privacy
protocol and reject a changed source, foreign reference or expired authorization.
Read must revalidate too: criteria/CV/analysis changes mark the position stale and
require deliberate reconfirmation; no automatic recomputation or silent version
substitution. A new confirmation records a new reviewed version, rather than
pretending an old judgment covered changed evidence. This is a proposed contract,
not a new write endpoint or implemented audit-history guarantee.

Treat free-text rationale as potentially derived protected data even if the UI
asks reviewers not to copy transcript quotations. When it depends on F5, use the
same or shorter retention boundary; withdrawal fences must immediately deny the
rationale/position/evidence links and cleanup must erase dependent rationale along
with source-derived material. An invalidation tombstone may retain minimal
non-content audit metadata only under an agreed policy. Keep a purely CV-based
confirmation separate from an invalidated mixed-source one; do not silently strip
F5 and claim the previous judgment remains valid. Hashes detect staleness; they do
not grant access or make protected rationale anonymous. The lifecycle design and
its privacy/concurrency tests must precede implementation.

### Limitations, changed files and viva

This increment is an evidence foundation, not full F6 acceptance. Recruiter
confirmation/persistence is not implemented. Full unscored F2 matches, historical
criterion descriptions without a retained snapshot, genuine CV-absent interviews,
explicit F5 analysis-version selection, portable PostgreSQL fixtures and full
native print/cancellation acceptance remain separate work. No missing evidence
was reconstructed or silently backfilled.

Changed files: backend report schema/service and report/discovery tests; frontend
report API contract, shared `ConsolidatedAssessment` view, new `SuitabilityEvidence`
component, print/screen CSS and report/comparison test fixtures; this document.

Viva: “F2 measures CV requirement coverage. F5 supplies saved qualitative findings.
The profile puts those authorized records beside each requirement, preserving
source links and missing-evidence labels. The system assembles evidence; the
recruiter makes and later confirms the overall judgment. An unavailable source
is missing information, not poor performance.”

## F6 Increment 5B — explicit recruiter confirmation (17 October 2026)

Implemented on `feature/f6-reviewer-confirmation` from verified Increment 5A
`5ef7e22317174b4cff8c948102b26215e5cee349`, in the primary checkout. The prior
5A pending-judgment text is historical: enabled reports now show the actual
pending/confirmed/stale/restricted projection. No numeric combination, ranking or
hire/reject action is introduced. Full F6 acceptance is not claimed.

Architecture and retention decisions: [reviewer confirmation ADR](architecture/ADR_f6_reviewer_confirmation.md).

### Retention audit before migration

`CandidateScoreRecord`, `InterviewSchedule.screening_snapshot`, filesystem CV
intake and the existing intake ledger were inspected. CV/application records have
no retention deadline or application-wide deletion route. Upload failure cleanup
is not candidate deletion. Interview sources already have consent, withdrawal,
retention and verified cleanup. No existing tighter CV retention policy conflicted
with the owner's approved development policy: confirmation maximum 30 days;
interview-dependent expiry is shortened to the source deadline. This is a project
engineering decision, not a trainer-approved or legal retention requirement.

There is still no application registry/deletion API. The new migration removes
confirmation after the exact application's last persisted score/snapshot is
deleted; it does not misrepresent deleting a filesystem CV as deleting surviving
historical evidence. Any future application/CV deadline must be integrated before
production acceptance. Existing private home databases were not migrated.

### Persistence and API execution

Migration `0015_reviewer_confirmation`, parent `0014_interview_analysis`, creates
`reviewer_confirmations`, one unique job/batch/upload row. It stores authenticated
reviewer ID, qualitative position, explicit requirement/source scope, typed reason
and evidence references, server time/expiry, criteria/source fingerprints, F5
version/dependency metadata and optimistic version. It stores no copied source
text, unrestricted rationale, names, contact fields or numeric total. F2 rows are
replaceable; therefore no confirmation FK points at them. Analysis IDs are
metadata and never prevent transcript-derived cleanup. There is no history table.

One explicit authenticated mutation:

```text
PUT /api/v1/jobs/{job_id}/batches/{batch_id}/candidates/{upload_id}/assessment/confirmation
```

Input: expected version (0 for no row), fresh report evidence token, position
`alignment|mixed|insufficient`, scope `cv_only|cv_interview`, reviewed requirement
IDs and typed references `{criterion_id, kind, reason, qa_id?, dimension?}`.
Free-text rationale or client reviewer identity are rejected as unknown fields.

The existing report reader freshly validates exact identity and sources under
job/interview locks. Mutation then locks the confirmation, checks version/token,
validates scope/references and computes dependency fingerprints. It flushes and
validates the safe response before committing. A mismatch returns 409, unsupported
claim 422, unauthorized recruiter/candidate 404/401, disabled/storage failure 503.
A commit/network outcome may be uncertain; the client must refresh and reconcile,
not automatically retry. The job lock plus unique key protects the no-row case.

### Evidence gates and source states

- Every mandatory requirement must be included, even for limited scope.
- Every scoped requirement needs an explicit evidence or gap rationale; the saved
  summary lists the complete reviewed scope, not only positively cited items.
- Alignment requires supported evidence for every scoped requirement. Excluded
  screening, ambiguous CV matches and scoped F5 concerns block alignment. A CV
  reference must be an original supported match. F5 support needs a supported
  completeness/technical-accuracy dimension, exact mapped question and non-uncertain
  topic mapping; relevance/articulation/topic mention alone cannot justify it.
- Mixed requires a concern/partial/uncertain finding, not merely missing evidence.
- Insufficient requires a validated missing/unassessed reference. It is abstention,
  never rejection. A fully unscored application cannot invent positive CV matches.
- CV-only scope is explicit and does not depend on F5. A newly available interview
  is outside that recorded scope until explicitly reviewed. No old mixed judgment
  is silently changed to CV-only after restriction.
- Missing/ambiguous/withdrawn/deleted/expired F5 cannot support interview scope.
  CV-only may still be independently confirmed from authorized CV evidence.
- Historical selection evidence remains reportable, but new confirmation requires
  matching current confirmed criteria. Truly missing applications still return 404.

### Read-time privacy, consistency and cleanup

Existing report GET now includes `confirmation`: pending, confirmed, stale or
restricted. Default-disabled serving returns pending with `enabled=false` without
querying the new table. Activation is development-only via
`REVIEWER_CONFIRMATION_ENABLED=true`; migrate the chosen synthetic database first.
No local .env or private home database was changed to activate it.

Every enabled GET validates current dependencies. Changed effective F2 evidence,
criteria or F5 source/result/version makes it stale. Later mutable F2 replacement
does not substitute a retained interview-selection snapshot. Expiry, withdrawal,
deleted/unavailable protected input, tampered dependency metadata or reviewer
association makes it restricted. Stale/restricted responses contain no active
position, scope, rationale references or reviewer identity/timestamps. GET performs
no writes, lease expiration changes, inference or external calls.

Withdrawal retains its durable interview fence. Confirmation-first commits can
become inaccessible immediately after withdrawal commits; withdrawal-first denies
confirmation. Existing cleanup deletes dependent confirmations before derived
analysis/source rows and verifies deletion. Failure leaves the fence denying reads.
A separate bounded maintenance loop removes expired/restricted/orphan confirmations,
even when confirmation/transcript serving is disabled. Reads do not depend on its
success. Runtime status is fixed operational text without content/SQL logging.

Deferred source-deletion triggers distinguish an F2 replace transaction from last-
source deletion. Job/reviewer/interview FK cascades and bounded orphan cleanup add
further protection. A physical purge removes the current version; a later eligible
read may be pending rather than a retained tombstone. No long-lived history is added.

### Recruiter workflow and rendering

Enable only in an approved migrated synthetic development environment. Open a
fresh consolidated report; choose reviewed sources, position, requirements and
original evidence/structured reasons. Mandatory requirements cannot be unchecked.
A separate acknowledgment and **Confirm reviewed suitability** click are required.
The server validates all choices; UI availability is not the authorization boundary.

Success refreshes the report. An uncertain result locks resubmission and provides
**Refresh and reconcile current state**. There is no background save, browser
storage or free-text field. The active confirmation shows source scope, reviewer,
time, expiry and reason labels, with original evidence IDs in audit details.
Single report, comparison and native print share the same summary, not independent
interpretations. Confirmation expiry also clears screen/comparison memory and
bounds the prepared print copy. Existing print preparation freshly reauthorizes.
Already delivered browser previews, PDFs or paper cannot be recalled.

### Executed tests and limits

A temporary local `f6_test_*` database was created on the already installed home
PostgreSQL server. It was upgraded base-to-head, downgraded to 0014, and re-upgraded
to 0015. The existing `talenttrace_home` database/schema and private records were
not modified. F6 fixture guards now also permit explicitly opted-in local
`f6_test_*` names; the legacy home guard remains available. No image/dependency or
model downloads were needed. Credentials were never logged or committed.

Focused backend command (with the temporary DATABASE_URL, F6_HOME_PG_TEST=1,
HF_HUB_OFFLINE=1 and TRANSFORMERS_OFFLINE=1):

```text
.venv/bin/python -m pytest tests/test_consolidated_assessment.py
 tests/test_candidate_comparison.py tests/test_assessment_discovery.py
 tests/test_comparison_snapshot.py tests/test_reviewer_confirmation.py -q --tb=short
```

**111 passed, 0 failed/skipped**: 26 unit cases and **85 PostgreSQL cases**.
New coverage includes three positions; supported/unsupported claims; mandatory
scope; forged questions/requirements; relevance/articulation exclusion; no free
text/reviewer spoofing; missing/unscored/history; CV-only; ambiguity; unauthorized
access; criteria/rescore/source/result changes; expiry; database retention bound;
restricted/stale projection; deferred deletion versus replacement; verified cleanup
and failed physical cleanup; stable no-write GET and no inference traps. Real
independent-connection cases cover simultaneous version updates and both orderings
of confirmation/withdrawal. Prior comparison MVCC/privacy tests also passed.

Frontend `pnpm test`: **231 passed, 0 failed/skipped**. Seven new tests cover safe
projection, all positions in report/print/comparison, stale/restricted suppression,
explicit UI/mandatory scope, one credentialed PUT without retry, confirmation print
expiry and memory-only uncertainty handling. `pnpm build` passed TypeScript and
Vite; the existing >500 kB LiveKit chunk warning remains. Early collection caught
a service parenthesis typo; it was fixed before the final passing commands. No
production constraint was weakened. Full backend/older office PostgreSQL gates
were not run. Native print-dialog cancellation and actual long F5 PDF pagination
are still not acceptance-verified by these markup tests.

An authenticated browser walkthrough used a separately seeded synthetic account
and CV-only application in the disposable database. Selecting the position,
requirement, original supported CV reference and acknowledgment enabled the
explicit mutation. The refreshed report showed the confirmed position, CV-only
scope, reviewer/time/expiry, structured reason and version 1. No actual interview,
new model call or real candidate was used. Screenshot: ignored local
`data/home/f6-reviewer-confirmation-verified.png`. This confirms the explicit
workflow, not native print-dialog behavior. After verification the temporary
backend/database were removed and the normal backend restored with confirmation
disabled; local .env and the existing home schema were left unchanged.

### Files and remaining acceptance

Backend: migration 0015; reviewer-confirmation model/schema/service/runtime;
model registration; config/main; report schema/service/router; transcript privacy
cleanup; new confirmation tests and two existing F6 fixture guards. Frontend:
confirmation API/component/tests; report contract/view/profile; comparison expiry
and native print deadline handling. Documentation: this file and the ADR above.

Remaining: full print cancellation/pagination, lost unscored F2 evidence, explicit
analysis-version selection, genuine CV-absent applications, full application-wide
retention/deletion policy, delegated reviewers, durable confirmation history and
production privacy/activation acceptance. The implemented record is a human
judgment over a specified evidence version, not proof of hiring suitability.

Viva: “The system validates the evidence, but the recruiter chooses the position.
The saved record identifies who reviewed which requirements and source versions.
Fingerprints detect changed evidence; authorization and retention still run on
every read. Withdrawal hides the dependent judgment immediately, even if physical
cleanup has to retry. Missing evidence is never converted into a low score.”

### Exact Increment 5B changed-file manifest

Paths are relative to `/home/shafi/Projects/TalentTrace-AI` (25 files):

- `backend/alembic/versions/0015_reviewer_confirmation.py`
- `backend/app/api/routers/consolidated_assessment.py`
- `backend/app/core/config.py`
- `backend/app/db/models/__init__.py`
- `backend/app/db/models/reviewer_confirmation.py`
- `backend/app/main.py`
- `backend/app/schemas/consolidated_assessment.py`
- `backend/app/schemas/reviewer_confirmation.py`
- `backend/app/services/confirmation_runtime.py`
- `backend/app/services/consolidated_assessment.py`
- `backend/app/services/reviewer_confirmation.py`
- `backend/app/services/transcript_privacy.py`
- `backend/tests/test_comparison_snapshot.py`
- `backend/tests/test_consolidated_assessment.py`
- `backend/tests/test_reviewer_confirmation.py`
- `docs/architecture/ADR_f6_reviewer_confirmation.md`
- `docs/f6_consolidated_assessment.md`
- `frontend/src/api/assessmentPrinting.ts`
- `frontend/src/api/consolidatedAssessment.ts`
- `frontend/src/api/reviewerConfirmation.ts`
- `frontend/src/components/CandidateComparison.ts`
- `frontend/src/components/ConsolidatedAssessment.ts`
- `frontend/src/components/ReviewerConfirmation.ts`
- `frontend/src/components/SuitabilityEvidence.ts`
- `frontend/tests/reviewerConfirmation.test.ts`
