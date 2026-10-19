# N19 Step 1 — submission inventory

**Implemented:** privileged administrative, read-only inventory of one exact
`recruiter_id + job_id + batch_id + upload_id` association. This is not candidate
deletion, a deletion authorization, or complete N19 acceptance.

The locally reviewed BID, PDF page 19, N19 requires a means to delete a candidate
and associated data; a documented administrative endpoint or script suffices.
There is no global candidate identity in the current schema. Do not group people
by name, email, filename or inferred similarity.

## Run

From `backend/`, using the project's Python environment:

```text
python -m app.candidate_inventory --recruiter-id RECRUITER_UUID --job-id JOB_UUID --batch-id BATCH_UUID --upload-id UPLOAD_UUID
```

All four UUIDs are mandatory. Configure `DATABASE_URL` and `CV_UPLOAD_ROOT`
privately using the existing Settings mechanism/environment; never put a database
password on the command line. `CV_UPLOAD_ROOT` is the common configured root,
**not** an already recruiter-scoped subdirectory. The script derives
`root/recruiter_uuid/job_reference/batch_uuid/upload_uuid.pdf` or `.docx`.

This is a **privileged administrative operation**, not an authenticated recruiter
API. Possessing database credentials authorizes the operator; supplying a
recruiter UUID does not authenticate a person. The tool checks that the specified
job belongs to that recruiter before inspecting submission files or records.
Prefer a SELECT-only database role with suitable metadata visibility and
read-only access to the private CV root. It works with normal existing database
credentials but explicitly opens a PostgreSQL `REPEATABLE READ READ ONLY`
transaction. It never invokes migrations, integrations, parsing or inference.

Exit 0 means inventory produced, **not** that deletion is safe. Exit 1 means a
fixed sanitized failure code; argument errors exit 2. No raw SQL exception,
database URL, contact address, token, transcript or CV content is printed.

## Output and associations

The JSON contains category counts with `confirmed`, `missing`, `ambiguous` or
`unsupported`, fixed reason codes and blockers. `confirmed` establishes a row's
explicit association, not the truth of evidence in its JSON. `missing` means no
matching row/file, not necessarily corruption: many categories are optional.

Confirmed counts include imported provenance/contact **records** (without
printing their values), all screening revisions, interviews and their copied
screening snapshots, scheduling/joining invitations, email attempts, transcript
sessions/turns/privacy capabilities, F5 analyses, F6 confirmations and application
acknowledgements. No PII-bearing payloads are loaded to construct output.

Shared bulk-operation rows are conservatively reported at job scope as
**ambiguous**: their preview/outcome JSON may contain several applicants. They
are not deletion targets. Reused batch/upload identities under other jobs are
also ambiguous, not automatically included. Unmapped foreign-key dependencies
are flagged; references without foreign keys and arbitrary historical JSON
cannot be exhaustively discovered.

Files are inspected by exact supported upload names, independently of other
uploads in the same batch. No contents/checksums are read. Links/junctions along
the path and multiple supported files are blockers; missing files are reported.
Historical nonstandard extensions/layouts, alternate storage roots, archived
exports and backup copies are not found by this tool. It never scans sibling
recruiter storage. Filesystem observations are not transactionally synchronized
with the database or safe against concurrent changes for future deletion.

An entirely unestablished target is flagged. Global candidate identity, external
Google/Drive/email copies and backups, F11 process-local state and other in-flight
work remain unsupported. Consequently every result has explicit completeness
limitations. A score-only synthetic/legacy association is not proof that an
uploaded application or CV exists.

## Tests

```text
python -m pytest tests/test_candidate_inventory.py -q
```

For the real PostgreSQL regression, set `N19_TEST_PG=1`. Docker must already have
the pinned pgvector image specified in the test (or `N19_TEST_IMAGE`). Tests use
`--pull=never`, a unique disposable container, loopback random port and no existing
volume. They migrate that disposable database only, then remove the container.
Windows link tests simulate the metadata guard if OS link privileges are absent.

Validated locally on 19 October 2026: **8 inventory tests passed**, including
the disposable PostgreSQL migration, CLI invocation, all-table before/after
digests, read-only SQL inspection, dependency discovery and owner-scope checks.
The existing interview-access/LiveKit suites also passed (**23 tests**).
Python compilation, CLI help and `git diff --check` passed. No application/demo
database was used for these tests. These are inventory tests, not deletion tests.

## Next increment — not implemented

Define candidate-wide versus submission-wide scope and introduce an authorized,
durable deletion fence covering all read/write/import/booking paths before any
cleanup. File deletion needs idempotent verified recovery outside database
transactions. Revoking application access does not revoke cached self-hosted
LiveKit tokens; active-media handling remains a separate unresolved safeguard.
No fence, deletion, cleanup, external removal or production activation is added
by this increment.
