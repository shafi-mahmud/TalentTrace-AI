# N19 Step 2 — maintenance preflight and manifest

**Implemented:** read-only administrative observations and a deterministic preview
for one exact owned submission. **Not implemented:** exclusive maintenance mode,
deletion intent/fence/tombstone, deletion, file cleanup, restart prevention or N19
candidate-wide completion. No migration is needed for this increment.

## Command and privileges

From `backend/`, configure `DATABASE_URL` and the common `CV_UPLOAD_ROOT` privately
using existing Settings. Never put passwords or candidate contact data in flags.

```text
python -B -m app.deletion_preflight --recruiter-id RECRUITER_UUID --job-id JOB_UUID --batch-id BATCH_UUID --upload-id UPLOAD_UUID
```

`-B` also avoids Python bytecode-cache writes. This is a privileged operator tool,
not recruiter login. It checks the declared
job/recruiter association, not the operator's human identity. Inventory uses the
existing read-only service. Other SQL observations use read-only transactions.
No role changes, session termination, permission changes, file writes, migrations
or service restarts are performed by the command. It creates ordinary temporary
database connections; PostgreSQL may record access in its normal statistics/logs.

Output contains current database/role names (administrative metadata), activity
counts, partial runtime hints and the manifest. Database credentials, query text,
client addresses, command lines, environments, scheduler arguments, candidate
contacts, CV/transcript content and capability values are never output.
Absolute storage paths are withheld; `configured_CV_UPLOAD_ROOT` identifies the
configured root and confirmed files use opaque root-relative paths.

Exit **1** means observed but blocked; exit **2** means essential observations are
unknown or arguments invalid. This increment never exits with a deletion-ready
success. Treat neither exit as permission to delete or shut down anything.

## What is actually checked

- PostgreSQL current database/role, superuser/create-role flags and membership in
  `pg_read_all_stats`.
- Other client sessions in that database, including idle connections, visible
  active sessions/open transactions and prepared transactions. The observation
  connection itself is excluded. Restricted statistics visibility is explicit;
  a zero count is not an exclusive-access guarantee.
- Storage root metadata availability and link/junction guards. This does not test
  write access or acquire an exclusive filesystem lock.
- Optional `psutil` process hints for TalentTrace Python/Node commands, local STT,
  LiveKit and other Python processes. The preflight process itself is excluded.
  Missing psutil leaves visibility unknown; no dependency is installed.
- Docker image-name hints from a bounded read-only `docker ps`, if available.
  This does not establish mount/configuration/target-database equivalence.

Scheduled launchers, supervisors, other machines, independent clients, loaded
environment configuration and in-process SMTP/F5 work remain **unknown** to the
generic collector. Matching a process does not prove it accesses this target;
not matching one does not exclude a writer. SMTP may already have been accepted
outside the process and cannot be rolled back. F11/caption work may be transient.
No inspection of microphone/audio/browser sessions is attempted.

The local design inspection on 19 October found Windows-host F11 components,
the existing separate Docker demo, multiple Git worktrees and the import CLI.
Windows scheduled-task enumeration found no matching launcher, not proof of
global absence. The configured source/target import bridge and optional separate
screening-checkpoint database require deployment-specific review. Checkpoint
threads lack a complete submission registry; unresolved copies block completeness.

## States and deterministic manifest

`preflight.state` is **blocked** when database observations succeeded but mandatory
controls are absent, and **unknown** when they could not be obtained.
`deletion_ready` is always **false**: exclusivity/restart enforcement is not built.

`manifest.status: ready_for_review` means only that a preview was produced. Its
versioned `plan` contains exact UUID scope, confirmed category counts, supported
root-relative filenames, shared bulk artifacts, missing/ambiguous/unsupported
associations, blockers and candidate-wide limitations. It contains no executable
SQL deletion instructions and no invitation/session hashes. Confirmed row counts
do not validate JSON evidence or prove exhaustive candidate-wide identification.

The plan digest is SHA-256 over canonical JSON. Reordering dictionaries or blocker
lists does not change it. Live connection/process statistics are outside the plan
digest, so they cannot masquerade as a stable cleanup authorization. The digest
is neither a signature nor a mutation lock. Filesystem and database observations
are separate; later deletion must revalidate identities and file paths.

Example (abridged, illustrative only):

```json
{
  "preflight": {
    "state": "blocked",
    "deletion_ready": false,
    "blockers": ["durable_restart_block_unavailable", "independent_writers_not_excluded"]
  },
  "manifest": {
    "status": "ready_for_review",
    "plan": {
      "scope": "exact_submission_only",
      "confirmed_database_associations": {
        "screening_versions": {"status": "confirmed", "count": 2, "reason": "exact_association"}
      },
      "deletion_authorized": false,
      "candidate_wide_deletion_resolved": false
    }
  }
}
```

## Dependencies before enforcement/cleanup

**Recommended, not implemented:** a distinct maintenance role, deployment-specific
control of all application connection roles and existing sessions, prepared-work
resolution, stopped workers/launchers, exclusive storage access and a durable
restart gate retained after failures. Establish least-privilege administrative
capabilities explicitly; even superuser status alone does not establish maintenance.
Independent superuser/OS-administrator bypass is outside any cooperative gate.

Future cleanup also requires durable operation/recovery state, import suppression,
shared-JSON association resolution, verified file/database absence and an explicit
external-copy/backup policy. Self-hosted LiveKit cached JWTs remain a limitation;
no media revocation guarantee is established by this preflight.

## Tests

```text
N19_TEST_PG=1 python -m pytest tests/test_deletion_preflight.py tests/test_candidate_inventory.py -q
```

The environment-assignment syntax above is for POSIX shells; in PowerShell set
`$env:N19_TEST_PG='1'` first. Tests reuse the unique disposable PostgreSQL fixture
with an existing pinned image and no existing volumes. They cover activity
detection, restricted-role visibility, exact ownership/file scope, stable sanitized
plans, unknown writers, unavailable resources and no candidate/file mutations.
Original inventory tests remain applicable to legacy ambiguity and unsafe paths.

Validated on 19 October 2026: **37 tests passed** across the maintenance preflight,
the original 8 inventory tests and 23 interview-access/LiveKit regressions. Python
compilation and diff checks passed. A read-only observation of the existing
isolated F11 database returned `blocked`, `deletion_ready=false`, two other client
connections, zero visible open transactions and an unavailable storage root.
The synthetic fixture's database manifest was available for review; this did not
establish a complete uploaded application or maintenance exclusivity. No existing
data, permissions or services were changed.
