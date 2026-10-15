# Application counts and in-app notifications

Trainer-requested increment: show job-specific received CV counts, new arrivals,
and an explicit mark-as-viewed action. UI redesign remains paused.

## Implemented data flow

F4 has **two existing persistence mechanisms**, not one application table:

* Native recruiter upload → `CvUploadService.store_batch()` → validated files
  under the configured root / recruiter UUID / job reference / batch UUID /
  upload UUID.pdf or .docx. Native uploads have no relational receipt ledger.
* Trusted application bridge → `ExternalCvImportService.import_submission()` →
  native private file plus `external_cv_submissions`. Database uniqueness on
  source/submission and batch/upload prevents duplicate trusted imports.

`GET /api/v1/jobs/{job_id}/applications` authenticates the recruiter and checks
job ownership before touching storage. It queries only non-personal ledger
columns for that job and discovers files in that recruiter's job directory.
It validates stored layout, bounded size and native file signature/package.
No CV text, email, filename, source response ID or score payload is returned.
The only returned identities are existing batch/upload UUIDs.

**CV received** means one persisted batch/upload identity. A batch containing
three files counts as three received CVs; three score versions for one file
still count as one. The union of native files and trusted ledger identities
counts a bridged file once. Trusted ledger records remain received if their
file is missing or its recorded type/size differs; they are separately marked
unavailable. An unsafe/invalid native batch is excluded and separately reported.
An unavailable imported record can therefore also have its batch reported as
needing review. Counts are not assertions about eligibility or file checksum.

No person-level deduplication is invented: uploading the same bytes again under
a new native identity counts as another received CV. Native filesystem storage
cannot establish a historical receipt after a file is removed, distinguish a
signature-valid orphan from a direct upload, or prove a candidate's identity.
This increment deliberately does not fabricate/backfill application rows.
Empty leftover directories are reported as invalid batches, not received CVs.

## Implemented new/viewed semantics

`application_views` stores a composite primary key of job/batch/upload.
There is no candidate data in this table, and the owner is derived from the job.
A received identity with no acknowledgement is **new**, regardless of whether
it is screened, excluded, eligible or unscored. Initially all existing identities
are new until explicitly acknowledged. No candidate, ledger or score is updated.

`POST /api/v1/jobs/{job_id}/applications/viewed` requires normal recruiter
authentication and mutation/origin protection. It accepts only the bounded
batch/upload identities in the displayed list, rediscovers current applications,
rejects unknown/cross-job identities and inserts acknowledgements with PostgreSQL
`ON CONFLICT DO NOTHING`. Repeating acknowledgement is safe. It cannot create an
application, change its review status or initiate screening.

The browser submits its displayed snapshot rather than “everything now”. An
arrival after that snapshot stays new. Count loading/refresh never marks viewed.
An ambiguous viewed request is not retried automatically; Refresh reconciles it.
Read state is shared across that recruiter's sessions/devices through PostgreSQL.

## Implemented UI and refresh

Candidate Screening shows a compact Applications section for the selected saved
job: CVs received, new badge, Refresh and View applications. The list uses anonymous
application numbers and availability/origin labels. Its explicit acknowledgement
button appears inside the opened list. No email, push or SMS notification exists.

Counts load on job selection and refresh after successful native upload, or on
explicit Refresh after a trusted import. There is no polling, queue or background
service. Each request makes at most two bounded queries and scans at most 1,000
job-directory entries / 1,000 applications; exceeding bounds is an explicit error,
never an apparently complete partial count. Acknowledgement lookup selects only
current identities, rather than all historical viewed rows. Filesystem scanning
and signature checks run in a worker thread. Concurrent imports may cause a
temporary storage warning; Refresh after import completion reconciles it.

## External-intake boundary

Google Forms intake is **not merged into F4**. This endpoint never calls Google
and never connects to the intake database. It includes Google-origin applications
only after the existing trusted bridge persists them into the selected F4 job.
It cannot count unimported remote Form responses or applications left solely in
the isolated intake worktree/database. The LinkedIn branch is also not integrated.

## Migration and verification

Migration `0011_application_views` adds only acknowledgement state, following
the existing `0010_interview_transcripts` branch head. It neither updates existing
records nor inserts initial viewed state. No demo database migration is applied
by this task. F4 reported previously at 0009 needs separate migration-readiness
review before activation: do not blindly apply all heads merely to enable counts.

Focused tests use synthetic files, mocked browser/network responses and an
explicitly opted-in disposable PostgreSQL container on port 54403. They cover
zero/multiple files, ledger/file identity deduplication, missing/invalid files,
new/viewed state, repeat acknowledgements, late arrivals, foreign jobs/recruiters,
authentication/mutation protection, score preservation and loading/error states.
No live Google, Groq, SMTP, interview or social publication is involved.

## Safe verification procedure

1. Use this separate worktree and a disposable database migrated through 0011;
   provide ignored private storage and synthetic recruiter/job fixtures.
2. Run backend/frontend on unused loopback ports, with matching API base and CORS.
   Leave original F4, intake and LinkedIn worktrees/services unchanged.
3. Sign in, select the synthetic job, open Candidate Screening: verify zero state.
4. Upload one synthetic PDF through the existing upload form: verify count/new=1.
5. View applications, mark listed applications viewed, Refresh: new=0.
6. Upload another synthetic PDF: received=2/new=1. Acknowledge the old list only:
   the new arrival must remain new. Reload/sign in again to verify persistence.
7. Verify another recruiter's job cannot be inspected or acknowledged.

**Live browser verification is not claimed.** Original demos remain unchanged;
schema activation and authenticated browser testing are separate next steps.

## Verification results (15 October 2026)

* 109 relevant backend tests passed; one existing optional bridge PostgreSQL test
  was skipped. The new notification test **did** run against disposable real
  PostgreSQL, including upgrade/downgrade/re-upgrade and record preservation.
* 170 frontend tests passed, including controlled component-handler tests for
  list, badge, acknowledgement, late-response cleanup and zero/loading/error states.
* Both TypeScript configurations, production build, Python compilation and
  whitespace checks passed. Vite reported the existing large interview-chunk warning.
* Read-only demo inspection confirmed F4 remains at `0009_bulk_scheduling` and
  intake remains at `0008_application_contacts`. No demo migration was applied.
  The disposable test container was removed after verification.
