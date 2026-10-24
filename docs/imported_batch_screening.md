# Trainer Sprint 5 — Screen stored imported CV batches

## Implemented

Candidate Screening now offers **Previously imported CV batches** for the active saved job. Confirm the current criteria and weights, explicitly load batches, review an available batch, acknowledge possible LLM quota use, then click **Screen imported batch**. Loading does not upload, re-import, mark applications viewed or invoke a model. Screening is never automatic.

The action reuses the existing authenticated F1/F2 POST endpoint, profile validation, matching graph, scoring arithmetic, score persistence and eligible-candidate scheduling selection. It does not manufacture a native upload response. Native uploads and saved-score loading remain available.

`GET /api/v1/jobs/{job_id}/imported-batches?revision=N` projects only owned job identity, criteria revision, batch/upload identities, availability, saved-result status and an opaque review fingerprint. It requires confirmed criteria. Discovery uses persisted `ExternalCvSubmissionRecord` identities, not names, CV contents, browser provenance or newest-row assumptions. Contacts, source identifiers, document contents, file hashes and private storage paths are not returned.

Stored files must match the exact ledger upload set, accepted document signature, size and SHA-256 digest under the existing safe recruiter/job/batch storage root. Missing, replaced, extra or unsafe files cannot be selected. Screening rechecks the review before model work and again before persistence. The existing owned-job row lock serializes concurrent requests; committed score replacement changes the review fingerprint, rejecting an unchanged duplicate review before another model call. The fingerprint is a freshness check, never an authentication credential.

Result status distinguishes not screened, current revision results, incomplete results and older revision results. Failed/uncertain operations never trigger a retry; reload saved scores and explicitly refresh/review before considering another attempt. Late responses after a job/criteria change cannot populate the new context.

No schema change: migration head remains `0017_booked_interview_email`. Existing import, consent, provider and scoring policies are unchanged.

## Verified — 24 October 2026

- Focused backend suite: **165 passed, 3 skipped, 0 failed**. Includes a connected real PostgreSQL scenario using real cookie authentication, CSRF checks, two jobs, trusted `ApplicationImportBridge`, actual PDF extraction, source-grounding, screening/scoring services and persisted reload.
- That scenario verifies foreign recruiter/job rejection, unapproved/stale criteria rejection, missing and same-size changed files, duplicate concurrent requests (one model invocation), file replacement during processing rejected before saving, failed extraction with no fabricated score, historical revision status and unchanged import count.
- Eight negative stored-file/association cases plus one valid-file case verify exact identities, status, missing/extra files, size, digest and signature protections.
- Frontend suite: **302 passed, 0 failed/skipped**. New cases cover strict response/redaction validation, explicit review and acknowledgement, duplicate suppression, failed screening, empty/unavailable states, late responses after context change, exact existing POST/header/body contract and foreign result rejection.
- Application and Vite TypeScript checks and production build passed. The existing large LiveKit chunk warning remains; it does not prevent the build.
- `git diff --check` passed.

External profile extraction is an explicit deterministic test double. The real extraction, grounding, graph, scoring, authorization and database services execute. External HTTP transport is blocked in the synthetic tests/lab. These results do not establish Groq accuracy, speed or quota availability.

The three skipped historical PostgreSQL cases require their own separate opt-ins/configuration (bridge concurrency, external intake concurrency and notification database tests). They were not counted as passes. The new Sprint 5 PostgreSQL scenario did execute against a newly named, test-owned container migrated only to 0017, with no host data/configuration mounted. The disposable helper now waits for TCP readiness instead of mistaking PostgreSQL's temporary initialization socket for the final server. An earlier run exposed that harness startup race; the final run passed.

### Actual browser verification

A separately created disposable PostgreSQL database and the built frontend served by the real FastAPI backend were used; frontend responses were not mocked. Only external model extraction was doubled. Synthetic jobs A/B and their imported files were prepared through existing trusted services.

| Journey | Result |
|---|---|
| Sign in, select job A, explicitly discover imported batches | PASS |
| Missing-file batch visible but not selectable | PASS |
| Review + quota acknowledgement + screen valid imported application | PASS; score 100 and source-linked results |
| Select eligible candidate for existing Interview Scheduling | PASS; correct job/candidate handoff; no booking/email/media trial |
| Switch to job B | PASS; A's batches/results cleared, only B's batch listed |
| Mobile review at 390 x 844 | PASS; no horizontal overflow |
| Synthetic profile-extraction failure | PASS; no score/eligibility fabricated; existing source-unavailable presentation |
| Read-only score reload and page refresh | PASS; current/incomplete statuses restored without rescreening |

Desktop inspection used a 1440 x 1000 viewport. Sanitized synthetic screenshots and lab artifacts remain ignored under local `data/validation/`; no screenshots, credentials, raw CVs or database files are committed. The agent-created browser tab and lab runtime were closed; its test-owned container was stopped. Preserved services/worktrees were not used.

## Limitations and next integration requirements

- Discovery is deliberately bounded to 100 imported records per owned job and 100 score-history rows per batch. Larger histories fail closed and need a separate pagination/review increment; nothing is silently omitted. Existing storage limits remain 20 files per batch, 10 MiB per file and 100 MiB per batch.
- Duplicate prevention covers the same reviewed state, not durable exactly-once provider execution. A crash before score persistence can leave the review unchanged. The operator must inspect saved results before an explicit retry, which may repeat provider charges. No new outcome or attempt ledger was added.
- Discovery reads/validates private files and holds the existing job lock; large valid batches may take time. This sprint does not claim a throughput benchmark or live-provider acceptance.
- The existing progress strip and native-upload panel still describe the native upload path; imported batches have their own explicit action and review above that panel.
- Live Google intake, real provider performance, SMTP, media and F11 were not exercised. Existing model configuration is still required for real screening.
- Recommended next step: review/fast-forward this isolated feature into develop under separate authorization, then repeat the recruiter walkthrough with the trusted intake deployment configured. No migration is required for this increment.

The previous integrated recruiter acceptance matrix was preserved separately on its existing acceptance branch in commit `86ed317`. It is historical evidence, not a substitute for the Sprint 5 checks above. No merge or push was performed.

## Changed code and test boundaries

- Backend: `api/routers/imported_batches.py` and `services/imported_batches.py` add trusted discovery/review; `api/router.py` registers it; `api/routers/screening.py` adds review guards around the existing workflow.
- Frontend: `api/importedBatches.ts`, the shared `api/screening.ts` request, `components/ImportedBatches.ts` and its `CvIntake.tsx` integration.
- Tests: new imported API/PostgreSQL and stored-file tests, imported frontend handlers/contracts, and the existing screening request tests. Legacy mocked-workspace fixtures explicitly model no import ledger; their SQL double supports the new read-only projection. The existing disposable PostgreSQL helper's TCP-readiness correction is test-only.
