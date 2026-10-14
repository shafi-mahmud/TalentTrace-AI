# F4 trusted application handoff

Implemented: `ApplicationImportBridge.import_application(actor_id, source_id,
submission_id)` is an internal service, not an HTTP endpoint or CLI. It is not
registered with the public HTTPS gateway. The local operator CLI accepts only a
submission key and explicit confirmation; it does not accept manifests, source/job
choices, recipient emails or provenance claims. Authenticated backend code supplies the
actor identity. Server-owned `BridgeBinding` values bind one source and source job
reference to an actual F4 recruiter/job ID/reference. Browser headers, manifests,
provenance strings and candidate names do not establish source trust.

The service invokes an injected trusted reader only after checking target ownership
and active recruiter status. The reader must authenticate/validate the intake ledger
and source owner and return the matching manifest plus bounded CV bytes. Implemented reader wiring now verifies the intake ledger through SELECT-only
database access and a read-only transaction, and verifies the exact private CV
size/type/SHA-256. A source role with write privileges is rejected. Source access
credentials and job bindings are not provisioned automatically. Real PostgreSQL
and synthetic storage tests exercise this reader; no demo import has occurred.

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

Next recommended increment: provision the implemented reader's SELECT-only source
role and private binding configuration, populate contacts through a separately
approved bounded operation, then approve F4 backup/migration readiness and one
synthetic import plus normal F4 screening. Bulk preview/send remains planned.


## Local operator configuration and command (implemented, not executed live)

Fixed ignored configuration: `data/application_bridge/configuration.json` in F4.
It must have private owner/SYSTEM/Administrator-only Windows file AND directory
permissions, be untracked and ignored, and contain exactly:

- `source_database_url`: secret SELECT-only asyncpg connection to the approved
  intake DB on loopback 54379; never reuse the existing writer connection.
- `target_database_url`: secret F4 asyncpg connection to loopback 54378.
- `source_storage_root`, `target_storage_root`: absolute operator-approved private
  storage roots, excluding the recruiter subdirectory (services add it).
- `binding`: `intake_recruiter_id`, `intake_job_id`, and `target` containing
  `source_id`, `source_job_reference`, `recruiter_id`, `target_job_id`,
  `target_job_reference`. Source and target IDs are independently verified.

From the F4 backend, using the existing private Python runtime:
`python -m app.application_import --submission <private-stable-submission-key> --confirm-synthetic-import`

Do not execute until configuration, source read-only role, available contacts and
F4 migration 0008 are approved and ready. The operator's private configuration/OS
identity establishes the local trust boundary. Target ownership is rechecked;
no frontend is trusted to declare original application contact provenance.
One invocation imports one submission, within a 30-second overall bound. Reader
work has a 10-second bound and CV bytes are capped at native 10 MiB. Symlink/junction
paths, extra batch files, unavailable contacts and altered bytes are rejected.
Output contains only import/reuse/status counts, not private identifiers or contacts.
It performs no Google, SMTP or Groq call and never copies source scores.

Live contact population remains separate. Existing intake import can fill NULL
contact provenance after verifying the same submission and local file, but currently
redownloads each CV. Recommended next intake increment: a bounded response-only
contact backfill using approved source, exact response-derived key, consent/job
checks and existing local file verification under the owned-job lock. It should
update only uninitialized contacts and reject conflicts; no Drive download or
candidate rescreening is needed. That command is NOT implemented here.
