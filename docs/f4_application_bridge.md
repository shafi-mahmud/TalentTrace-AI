# F4 trusted application handoff

Implemented: `ApplicationImportBridge.import_application(actor_id, source_id,
submission_id)` is an internal service, not an HTTP endpoint or CLI. It is not
registered with the public HTTPS gateway. Authenticated backend code supplies the
actor identity. Server-owned `BridgeBinding` values bind one source and source job
reference to an actual F4 recruiter/job ID/reference. Browser headers, manifests,
provenance strings and candidate names do not establish source trust.

The service invokes an injected trusted reader only after checking target ownership
and active recruiter status. The reader must authenticate/validate the intake ledger
and source owner and return the matching manifest plus bounded CV bytes. Production
reader wiring and its source access credentials are NOT implemented in this increment;
there is no live import command. Fake readers exercise the handoff in tests.

The manifest retains source/submission identity and application contact provenance,
MIME, length and SHA-256. Missing/invalid contacts remain unavailable. Respondent
input is not mailbox ownership verification. Intake batch IDs, candidate names,
filenames and screening scores are not used to assign F4 identity. No filesystem
paths or contact response endpoint is exposed to browsers.

Native `CvUploadService` validates/stores bytes under the target recruiter's private
job directory and creates new UUID batch/upload IDs. A new F4
`external_cv_submissions` row records source job and target job plus those identities
and contact fields. Target ownership is derived through `job_profiles.recruiter_id`.
The import uses the same owned-job lock and DB uniqueness guards as the tested
internal intake design. Retry verifies file integrity, reuses the row/file, and rejects
changed contact/source-job/file data. Failed writes roll back and remove only the new
batch. Uncertain commit acknowledgement preserves storage for operator reconciliation.

Import does not screen or send email. Existing authenticated screening resolves the
F4 job/batch and current confirmed snapshot; saved results retain actual F4 upload
and criteria revision. Screening remains a separate authorized step, and intake
scores are never copied. Tests use mocked profile/model dependencies.

Migration `0008_application_bridge` follows F4's `0007_interview_email`; it creates
only the new ledger. It was tested on disposable PostgreSQL with concurrent imports.
It has NOT been applied to the demo on 54378. Existing jobs, scores and interviews
are not backfilled or modified. No intake database writes or branch merge occur.

Next recommended increment: implement one explicit, local server-side intake reader
with read-only source DB credentials and configured private source storage. Verify
source recruiter/job, contact validation/provenance, exact ledger/file checksum and
submission key before returning the handoff. Then approve migration/backup readiness
and one synthetic import + normal F4 screening. Bulk preview/send remains planned:
current eligible scored results only, explicit cohort approval, recipient allowlist,
deduplication and exclusion of previous attempts/bookings/uncertain contacts.
