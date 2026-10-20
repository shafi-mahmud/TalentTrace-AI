# N19 increment: guarded deletion of one imported submission

**PARTIAL N19.** Based on published `4d37ba5`. This implements a deliberately
bounded administrative deletion, not a person-wide candidate erasure feature.
No global candidate registry exists. Never infer person identity from a name,
email, content hash, batch ID or upload ID alone.

## Supported scope and safeguards

`docker/n19_delete.py` accepts the explicit recruiter/job/batch/upload UUID tuple.
Only the labelled disposable N19 lab is supported: database `n19_lab`, maintenance
role `n19_maintenance`, UID 10002, private `/cv`, verified maintenance marker,
application role NOLOGIN and no other database clients/prepared transactions.
The host controller reuses `n19_lab.check`: unexpected mounts or application UID
processes fail closed. This is not a production/home-database activation command.
Docker/host administrators and the maintenance operator remain trusted.

The selected submission must have exactly one imported ledger record and exactly
one supported, regular, singly-linked CV file, whose bytes match its saved digest.
An owned job and complete existing inventory are required. Interview/scheduling
records, shared bulk JSON, cross-job reuse, missing schema dependencies and unknown
foreign-key dependencies block execution. Other application files/rows are not
included. The generic inventory/preflight still never authorizes deletion.

The first implementation cleans all F2 versions, application acknowledgements,
CV-only F6 confirmation and the exact external-intake ledger row for that tuple.
It refuses interview-bearing submissions rather than guessing how to invalidate
LiveKit tokens or selectively edit shared JSON. No Groq/transcription/network calls.

## Command flow

1. Host controller validates lab labels, mounts and maintenance controls.
2. `preview` reuses inventory and hashes a canonical plan: exact scope, counts,
   file digest and external source identity digest. Output has no source text,
   contact value, token, credential or absolute CV path. Save the digest privately.
3. `execute` requires `--confirm-exact-submission` and `--expect-digest`. Owner,
   maintenance, inventory, file integrity and digest are revalidated. The final
   inventory runs in the write transaction under NOWAIT exclusive locks on the
   known source tables. The lab is already offline: table locks add a fail-fast
   check, not a substitute for closing database and filesystem writers.
4. One transaction inserts a minimal replay fence/retry journal and deletes the
   selected rows. FK/SQL errors roll back both journal and cleanup. Commit happens
   **before** unlinking the CV; unrelated data is never recursively removed.
5. The exact CV is revalidated, unlinked and its parent directory fsynced. Absence
   of all known tuple-associated rows and this file is checked before marking the
   journal `complete`. Maintenance stays closed on success and failure.

`submission_deletions` (migration `0016_submission_deletion`) is intentionally
small: exact UUID scope, source/file/plan SHA256 digests, job reference, file type,
state and timestamp. No email, quotations, CV/transcript content or raw external
submission ID. These are pseudonymous identifiers/fingerprints, **not anonymous
data**; access/retention policy is still required before non-synthetic use.
No ORM entity is needed by the administrative SQL service. No source deletion
journal is exposed in the recruiter API. Downgrade refuses a nonempty journal so
it cannot silently erase replay suppression.

## Re-import fence

`ExternalCvImportService.import_submission` checks the tombstone under the existing
owned-job lock, before fingerprinting/storing a new CV. `ApplicationImportBridge`
reuses this importer. A PostgreSQL BEFORE INSERT/UPDATE trigger independently
rejects the same external `(source_id, external_submission_id)` even with new
batch/upload IDs. The digest uses explicit NUL-separated UTF-8 fields and built-in
PostgreSQL SHA256; no extension or remote service is added. Existing 0015 databases
without the new deletion feature keep their importer behaviour. Once journaled,
nonempty downgrade is blocked.

This does **not** suppress a manual reupload or a new external identifier/source
for the same human, nor erase the upstream source. Global/person-wide identity and
new-submission suppression are not solved by silently matching an email/hash.
There is no automatic admission-reopen command in this increment.

## Recovery / failure behaviour

- Before SQL commit: rollback leaves the source file/rows unchanged.
- Uncertain commit response: retry the **same tuple and saved plan digest**; never
  create a new target or reopen application access to inspect it.
- After commit, before unlink: durable `file_pending` remains with the replay fence.
  Retry verifies that journal's owner/digest, removes only the matching exact file,
  then verifies absence and marks complete. No deleted content is copied into the
  journal, so this is resumable cleanup, not restoration of erased source data.
- Changed bytes, hardlinks/symlinks, another client, unexpected mounts or remaining
  rows fail closed. Restore only an independently verified synthetic test fixture
  during tests; production recovery needs an approved process.
- Crash after unlink: a retry accepts the already absent exact file, verifies SQL
  absence and completes. Repeating a completed command is idempotent.
- Offline archives, WAL/physical disk remnants, upstream copies and already exported
  PDFs are outside this logical local-deletion scope. Secure erasure is not claimed.

## Isolated synthetic use

Use existing images only. Never attach an existing database/storage volume:

```bash
python3 -B docker/n19_lab.py init --state data/n19-maintenance/lab.json \
  --confirm-new-disposable --backend-image talenttrace-home-viva-backend:latest
```

This opt-in image selector avoids an office-specific image tag; no image is built
or pulled. The lab mounts **this worktree's** backend read-only, migrates only its
new database to 0016 and limits the application role to SELECT on the journal.
For a real approved lab fixture, enter/check maintenance using the existing
controller before invoking the CLI. Supply all four actual synthetic UUIDs:

```bash
python3 -B docker/n19_delete.py preview --state data/n19-maintenance/lab.json \
  --recruiter-id OWNER --job-id JOB --batch-id BATCH --upload-id UPLOAD
python3 -B docker/n19_delete.py execute --state data/n19-maintenance/lab.json \
  --recruiter-id OWNER --job-id JOB --batch-id BATCH --upload-id UPLOAD \
  --confirm-exact-submission --expect-digest SAVED_PREVIEW_DIGEST
python3 -B docker/n19_delete.py status --state data/n19-maintenance/lab.json \
  --recruiter-id OWNER --job-id JOB --batch-id BATCH --upload-id UPLOAD
```

Tokens above are placeholders. A failed/partial run leaves resources for diagnosis;
never repeat initialization or restore LOGIN automatically. State files contain
private generated lab credentials and must remain ignored/restricted.

## Testing and remaining work

Offline tests cover exact plan identity, incomplete/ambiguous scope, unsafe files,
CLI confirmation, sanitization and importer compatibility. The opt-in
`docker/n19_deletion_acceptance.py STATE` runs only against a fresh labelled lab;
its seed requires the exact new schema and zero recruiters. It creates fictional
fixtures, exercises deployed controls, then actual deletion and retry scenarios.
Do not run that destructive harness against any other environment.

Still required: candidate-wide identity/selection contract, manual upload lifecycle,
interview/session/transcript/F5 dependency cleanup with trustworthy media-access
invalidation, shared JSON handling, comprehensive re-import policy, production
operator authorization/retention and external-copy governance. N19 is not complete.

## Verified home increment — 20 October 2026

- Focused offline backend run: **87 passed, 36 skipped, 0 failed** across
  submission deletion, inventory/preflight, intake/bridge/reader, discovery and
  consolidated report tests. Skips require separately gated PostgreSQL fixtures;
  they are not counted as passes. No frontend code changed.
- Two **new** labelled labs used existing local images and their own fresh PG/CV
  volumes. The final fresh-lab run passed **15 destructive synthetic scenarios**:
  wrong owner/missing target, interview refusal, cross-job identity reuse,
  changed manifest, ambiguous CV/shared JSON, independent DB client, selected
  F2/acknowledgement/F6/ledger/file cleanup, SQL replay fence, idempotent retry,
  changed bytes during retry, post-commit interruption recovery, unrelated survivor
  and importer replay suppression.
- Six existing deployed maintenance checks passed: separate non-superuser roles,
  active writer refusal, closed application DB admission, application storage
  denial, unexpected volume-mount refusal and maintenance across worker restart.
- Three actual CLI checks passed: status, completed-command retry and a preview of
  the preserved unrelated submission. Nonempty-journal downgrade was refused and
  the lab revision stayed 0016. Syntax checks and `git diff --check` passed.
- Initial fixture errors (invalid scoring weights and SQL literal binding) were
  corrected; their transactions rolled back. Labs/failure diagnostics were
  retained rather than resetting a database. Destructive verification ran only on
  synthetic records in those new labs. No release migration or source/runtime
  configuration was changed; release remains on its separate 0015 deployment.

Remaining status is **PARTIAL N19**. This is meaningful actual deletion and replay/
retry protection for a narrowly defined scope, not complete candidate erasure.
