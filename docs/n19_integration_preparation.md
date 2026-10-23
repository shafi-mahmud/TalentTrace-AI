# N19 guarded deletion: integration preparation

## Provenance and supported scope

Prepared from verified origin/develop `480184c2321c6520bbb00754d1aa5a054003c03e`
on 23 October 2026. Reference origin/codex/n19-guarded-deletion:
`44c1b0b41f7ed9cdc0d25d47691f2cc6de15fb90`.
No merge or deployment is implied; this is a separate feature branch.

Ported the existing inventory/preflight, maintenance controller, administrative CLI,
deletion service, migration, importer fence, tests and supporting documentation.
The reference README was not copied over newer integrated release documentation.
No candidate/interview ORM models, F2 arithmetic, F6 projection, F11 or frontend
were changed. Screening-outcome-clarity is not included.

Implemented scope remains one exact recruiter/job/batch/upload tuple with one
supported imported ledger row and one regular, singly-linked, digest-matching CV.
The service deletes its F2 revisions, acknowledgement, CV-only F6 confirmation and
import ledger, then its exact file. It preserves unrelated submissions and the job.
It refuses interview/scheduling associations, shared artifacts, ambiguous files,
cross-job references and unknown foreign-key dependencies. No public deletion API.

## Maintenance and privacy boundary

Only the labelled Linux Docker N19 lab is supported: n19_lab database,
n19_maintenance non-superuser role, UID 10002, private /cv storage and verified
maintenance marker. Application DB admission and storage access must be closed,
other clients/prepared transactions absent, and mounts/processes verified by the
existing controller. Generic inventory/preflight never grants deletion readiness.
Docker/host administrators remain trusted; this is not protection against them.

The exact reviewed manifest digest and explicit confirmation are required. SQL
cleanup and a minimal file_pending tombstone/journal commit together. File removal
follows commit; retries use the same tuple/digest, validate integrity and absence,
then mark complete. Maintenance stays closed on both failure and success.
The source digest suppresses the same external source/submission on re-import;
the importer checks under the owned-job lock and a DB trigger protects ledger writes.
Journal identifiers/digests are pseudonymous, not anonymous; protect and retain them
under an explicit operator policy. No CV text, email, bearer or transcript is stored
in the journal. The CLI emits fixed errors rather than raw exceptions.

## Migration and deployment prerequisites

One Alembic head: 0016_submission_deletion, directly after
0015_reviewer_confirmation. No revision collision or renumbering. No migration was
applied here. A future approved upgrade adds the journal and external-ledger trigger;
ordinary application-role privileges must support the fence lookup/trigger.
Existing 0015 importer behavior is retained when the journal table is absent.
Downgrade refuses a nonempty journal, deliberately preserving suppression/recovery.
Do not run upgrade/downgrade or the destructive harness against a preserved database.

Next deployment validation must use fresh labelled database/storage volumes and
the existing [guarded deletion procedure](n19_guarded_submission_deletion.md).
No existing lab, application volume or interview may be reused for acceptance.
Review privileges and rehearse 0015-to-0016 plus importer behavior before integration.

## Verification and limits

Focused validation: **103 passed, 37 skipped, zero failed**, 12.64 seconds.
Skips: one Windows symlink-privilege case; four opt-in PostgreSQL inventory,
preflight, intake and bridge cases; 32 opt-in PostgreSQL F6 cases. No skip counts
as a pass. The initial run failed solely on Windows symlink privilege before the
test split; final results above include the corrected platform handling.

From backend, using the existing compatible Python environment:

```text
python -B -m pytest tests/test_n19_integration_compatibility.py tests/test_submission_deletion.py tests/test_candidate_inventory.py tests/test_deletion_preflight.py tests/test_external_cv_intake.py tests/test_application_bridge.py tests/test_candidate_scoring.py tests/test_score_integration.py tests/test_consolidated_assessment.py tests/test_assessment_discovery.py -q -rs
python -B -m alembic heads
python -B -m alembic history -r 0015_reviewer_confirmation:head
```

N19_TEST_PG was explicitly disabled for this run. Offline Alembic SQL rendering
from 0015 to 0016 verified journal/trigger DDL without connecting to PostgreSQL.
Python syntax, changed-document local links and diff whitespace checks passed.
No frontend build was needed because no frontend file changed.

New offline integration tests use SQL/session doubles
for wrong ownership, interrupted file_pending recovery, idempotent absent-file
completion, changed digest/manifest rejection, importer refusal before CV reading,
normal-host refusal and unique migration ancestry. They do not prove real SQL
rollback, transaction concurrency, directory fsync or Docker isolation.

The reference filesystem test is split so unsupported Windows symlink creation
skips only that case; hardlink and regular-file assertions remain executable.
Historical Linux lab results in the ported documents describe the reference branch,
not fresh acceptance of this integrated tree. No destructive acceptance or live
database test was run in this preparation.

Remaining BID N19 gaps: manual uploads, interview/transcript/F5-related cleanup,
person-wide multi-application resolution, shared JSON cleanup, production operator
and retention policy, manual/new-source reupload suppression and external copies/
emails/backups. Cached LiveKit JWT invalidation is not guaranteed. These unsupported
cases remain refused; there is no claim of full candidate deletion compliance.

## Deployed synthetic acceptance — 23 October 2026

Supersedes the preparation-only pending-lab statement above. One owner-authorized
session tested commit `07c06eb1b91a0032a764a5097a51bb362824f163` in a NEW Linux
Docker lab, `tt-n19-lab-5224de2b41`. Generated network/container/volume names were
checked unused before creation. No old lab or application volume was reused.

Existing local backend image: `db2a3ef6c3e9` (Python 3.12, /app/backend);
PostgreSQL/pgvector image: `cf134a767f47`. No image pull/build or dependency download.
A network-none, volume-free prerequisite check confirmed installed backend imports.
The new lab has an internal network, no published ports, new labelled PG/CV volumes
and a read-only mount of this branch's backend. Migration 0016 was applied only to
this fresh empty n19_lab database. Both application and maintenance roles are
non-superusers; maintenance retains the documented delegated role-management power.

Actual deployed results (not mocked tests): **24 checks passed, zero failed/skipped**:

- Six controls: non-superuser roles, active writer refusal, closed application DB
  admission, denied application CV-storage access, unexpected-mount refusal and
  maintenance preserved across restart of this newly created worker only.
- Fifteen scenarios: wrong owner, missing target, interview-associated refusal,
  cross-job identity reuse refusal, changed manifest refusal, ambiguous-file refusal,
  shared JSON refusal, concurrent-client refusal, selected related-row/file deletion,
  SQL replay trigger, completed retry, changed-file retry refusal, post-commit
  interruption recovery, unrelated submission survival and importer replay refusal.
- Three CLI checks: completed status, completed-command retry and unrelated-submission
  preview. The controls phase's no_candidate_data_deleted flag describes that phase
  only; subsequent acceptance deliberately deleted newly seeded synthetic data.

Read-only post-verification confirmed both target journals complete; zero supported
F2/acknowledgement/F6/import-ledger rows for those tuples; both exact target CVs
absent; survivor has its two expected score versions/values, acknowledgement and
ledger, with original synthetic CV bytes and matching stored digest. Both deleted
external source identities remain suppressed. Application admission remains NOLOGIN;
maintenance marker/storage isolation checks still pass. No admission was reopened.

Controller/harness commands used this session, from the worktree root:

```text
python -B docker/n19_deletion_acceptance.py data/n19-acceptance-20261023/lab.json
```

Initialization used the existing n19_lab.init controller with the explicit local
backend image and a wrapper that checked generated resource names before creation.
Do not rerun initialization or the fresh-only seed/harness on this retained lab.
Private state, container baseline and sanitized acceptance summary remain ignored
under data/n19-acceptance-20261023/. State contains generated lab credentials and
must not be published. Containers and volumes are deliberately retained for review.

All pre-existing containers retain their IDs/images/running states/start timestamps.
Existing host services were not restarted or reconfigured. No F11 replay, provider
request or migration of an existing database occurred. The internal network and
provider-free harness prevent dependency on external AI/STT; no packet-level capture
was performed. Output contains fixed check categories, not candidate text or tokens;
generated lab secrets were absent from retained container logs in the targeted scan.
This is bounded inspection, not a universal secret-detection guarantee.

The remaining unsupported cases above still apply. Successful exact imported-
submission deletion does not establish person-wide erasure or production readiness.
N19 is **PARTIAL**, now ready for a later reviewed integration decision. Next mandatory
work should address the full-duration F3/F4-to-F5/F6 workflow and its reproducible
deployment; do not unfreeze F11 or weaken deletion scope to obtain a broader claim.
