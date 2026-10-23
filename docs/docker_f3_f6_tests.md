# Opt-in Docker F3–F6 service integration tests

## Implemented scope

A separate `compose.f3-f6-test.yaml` runs the existing connected F3–F6
scenarios inside a test-only backend image. It does not enable features in the
production Compose project. Never combine the two Compose files.

Runner → `db:54402` uses a project-scoped **internal** network, without host
ports, bind mounts, external volumes, Docker socket or host environment files.
PostgreSQL uses a new project-scoped named volume. The intentionally passwordless
`trust` setting is restricted to this disposable synthetic network; it must never
be used for production or attached to another network. There are no reusable
credentials. The runner is non-root with a read-only root filesystem and `/tmp`
tmpfs. It receives no provider keys. HTTP provider transport is denied in the
connected scenarios, socket connections are restricted to the resolved database
address/port, and the internal Docker network prevents Internet routing.

The fixture checks database/user/port identity and an empty public schema before
migration. A transaction and advisory lock reserve a persistent one-shot marker
in a separate schema. A consumed or populated database is refused, including after
an interrupted migration. No automatic retry, teardown or repair occurs.
Only this verified new database is upgraded to the code's single Alembic head.
The reviewed contract is explicitly `0016_submission_deletion`; a missing, changed
or multiple head fails closed and requires test-contract review. The complete
resulting revision list must equal that single head. Migration failures propagate
to pytest and Compose's `--exit-code-from runner`.
The original host-based PostgreSQL fixture and production source are unchanged.

## Prerequisites and reproduction (PowerShell)

Use the reviewed core integration checkout, Docker Desktop Linux engine and
Compose v2. Inspect resource ownership and free disk/memory first. This measured
run had approximately 924 GB free host disk and 4 GB available host memory.
No preserved services need to be running. No frontend, LiveKit, Whisper model,
Groq key or AssemblyAI key is needed.

A locally built production backend dependency image named
`talenttrace-docker-demo-backend:latest` is required. On a clean machine, build it
explicitly with `docker build -f docker/backend.Dockerfile -t talenttrace-docker-demo-backend:latest .`
after reviewing dependency download requirements. This does not start the
production application. The test image overlays the current checkout's app and
migrations, avoiding stale base-image source. Its only added package requirement
is the existing dev pin `pytest==9.1.1`; pip also installs pytest dependencies.
Production Dockerfiles do not copy tests or add these dependencies. Model weights
are not downloaded. The Docker context allows Python tests while keeping final
private-data exclusions in force.

From the repository root, choose a new identity for **each** test execution:

```powershell
$env:F3_F6_TEST_PROJECT='tt-f3f6-test-'+([guid]::NewGuid().ToString('N').Substring(0,12))
docker volume inspect "$($env:F3_F6_TEST_PROJECT)_test_data"
# Expected: no such volume. STOP if it exists; do not reuse or remove it.
docker compose -p $env:F3_F6_TEST_PROJECT -f compose.f3-f6-test.yaml config --quiet
docker compose -p $env:F3_F6_TEST_PROJECT -f compose.f3-f6-test.yaml build --pull=false runner
docker compose -p $env:F3_F6_TEST_PROJECT -f compose.f3-f6-test.yaml up --no-build --pull never --abort-on-container-exit --exit-code-from runner
$LASTEXITCODE
```

Review rendered configuration before `up`: only db/runner services, internal
network, no published ports, no bind/external volumes. Confirm the generated
project is absent from existing container/network/volume inventories. Do not
supply an arbitrary database URL. The fixed internal port retains the original
connected test's database identity contract; it is not published on the host.
`--exit-code-from runner` propagates pytest failure. Compose stops only this
project's containers on completion; containers, named volume and logs remain.
Do not rerun a consumed database. On failure preserve logs and inspect before
requesting another execution.

## Historical 0015 verification — 23 October 2026

Source starting point: `43a5847b340baceef0b095d6132b5057400e168c`.
Project: `tt-f3f6-test-1a44244f8a2b`.
Dependency base image: `db2a3ef6c3e9b99c424fdb6a59b959787e77aed8fbcabcd8eb480ad98da8aca3`.
Added packages: pytest 9.1.1, iniconfig 2.3.1, pluggy 1.7.0; pip check passed.

| Check | Actual result |
| --- | --- |
| Container connected scenarios | 8 passed |
| Container epoch contracts | 8 passed |
| Combined container invocation | 16 passed, 0 failed/skipped; 9.34 s; exit 0 |
| Offline fixture safety guards | 19 passed, 0 failed/skipped (final guard run) |
| Existing Docker readiness/verifier regressions | 8 passed, 0 failed/skipped; 1.05 s |
| Migration | Fresh test DB upgraded to 0015; repository has one head |
| Runtime inspection | Unique Compose labels, internal network, own volume, no host ports/binds, runner read-only, no provider keys |
| Production baseline | Compose renders; three original services, disabled feature flags, private networking and production Dockerfiles unchanged |

Commands for offline regression, from `backend/`:
`python -B -m pytest tests/test_docker_f3_f6_guards.py -q --tb=short`
and `python -B -m alembic heads`.
From the repository root:
`python -B -m pytest docker/test_readiness.py docker/test_verifier.py -q --tb=short`.
The first guard-test invocation from the repository root failed collection because
`app` was not on the import path; using the documented backend working directory
passed. A final disabled-mode guard was subsequently added and the 19-test guard
suite passed. This was not a connected-container failure or retry. The authorized
connected execution ran once. No production startup/rebuild was performed.
Private run log/project identity/exit status remain in ignored
`data/docker-f3-f6/`. Both new containers stopped through Compose's normal
completion behavior; their volume and diagnostics are retained.

## What the tests prove, and limits

Real application services and PostgreSQL verify authenticated scheduling,
submission association, independent storage consent, attributed transcript
persistence/finalization/retrieval, F5 LangGraph evaluation, F6 persisted reload,
wrong owner/job/application rejection, partial/missing evidence, provider failure,
two bounded epochs, gap warnings, overlap rejection and consent withdrawal.
The recognizer and evaluation model are deterministic synthetic test doubles.
Candidate session identity is seeded synthetically, not claimed in a browser.

This is **not** browser audio/video acceptance, real speech recognition accuracy,
real Groq evaluation, full-duration interview acceptance, or complete clean-machine
F1–F6 deployment. Production full-feature Docker still needs separately reviewed
LiveKit configuration, local STT dependencies/model provisioning, consent/feature
configuration and a safe F5 inference strategy (the baseline internal network
cannot reach Groq). Automatic bounded capture continuation remains unimplemented;
120-second default/300-second maximum capture limits remain unchanged. These tests
do not enable F11 or integrate N19.

## Recommended cleanup — separate authorization required

Retain failed evidence first. Verify the exact project's container, network and
volume Compose ownership labels. Only after explicit cleanup approval, with the
recorded identity still selected, use:

```powershell
docker compose -p $env:F3_F6_TEST_PROJECT -f compose.f3-f6-test.yaml down --volumes
```

This deletes that synthetic project's data; it was **not executed** in this task.
Never use global prune, shared volume names or a preserved project identity.


## Combined N19 schema verification — 23 October 2026

Supersedes the earlier runner's 0015-only limitation. Increment A is
`fe54a6f687ccbbb85641a0afeb495fa0a160ecd4`. Increment B uses the same Compose
commands above; no production Compose or application behavior was changed.
`docker/f3_f6_container.py` now derives the unique code head, requires the reviewed
0016 contract, renders existing migrations, executes them only after the fresh-DB
reservation, and verifies every stored revision. No migration revision was added.
Chain: `0014_interview_analysis → 0015_reviewer_confirmation → 0016_submission_deletion`.

The one authorized execution used new project `tt-f3f6-test-d356c9a3ff3a`.
Before creation, both container names, the network and named volume were absent.
Rendered configuration and post-run inspection verified only the two lab services,
internal network, new project-owned volume, no host ports, no host binds/env files,
non-root read-only runner, no provider keys and no external inference dependency.
The cached dependency installation layer was reused; no model was downloaded.

| Final invocation | Passed | Failed | Skipped | Deselected |
| --- | --- | --- | --- | --- |
| Increment A migration test | 1 | 0 | 0 | 53 |
| Increment A Docker readiness/verifier | 9 | 0 | 0 | 0 |
| Increment B host safety + mocked N19 compatibility | 35 | 0 | 0 | 0 |
| Increment B Docker readiness/verifier | 9 | 0 | 0 | 0 |
| Combined container run, 11.76 seconds, exit 0 | 25 | 0 | 0 | 0 |

These are per-invocation counts, not unique tests to sum. The container's seven
mocked N19 compatibility cases also occur in the host run; the readiness suite is
repeated across increments. The 53 deselected tests were unrelated PostgreSQL
transcript scenarios excluded from the focused Increment A command, not failures
or passes. No tests were skipped in these final invocations.

Container breakdown: eight real-service F3–F6 PostgreSQL scenarios, eight epoch
contracts, two real PostgreSQL N19 schema/replay checks and seven mocked N19
compatibility cases. The schema check verifies revision 0016, journal columns and
the enabled ledger trigger. The replay check calls actual `import_suppressed`,
inserts a synthetic journal row in a rollback-only transaction, verifies exact
source suppression and unrelated-source allowance, then exercises the real trigger
function on a temporary table. Expected SQLSTATE 23514 is caught within a savepoint;
the log's `external_submission_deleted` error is this successful negative check.
The journal row and temporary table are rolled back; zero journal rows remain.
No candidate record or CV was deleted and no destructive maintenance path was
entered against PostgreSQL. Mocked recovery tests use temporary synthetic files
and session doubles, not real database deletion.

Host guard coverage includes obsolete/future/multiple code heads, mismatched or
multiple stored revisions and a migration exception that escapes before final
revision checking. Failure propagation uses normal pytest status and Compose's
existing exit-code mechanism; a failing live migration was not deliberately run.

Private project identity, exit status, baseline container metadata and run log are
retained under ignored `data/docker-n19-schema/`. Both new containers stopped
through normal Compose completion; their volume, containers and diagnostics remain.
Preserved container IDs/images/start times and host runtime listener PIDs matched.
Production configuration renders with unchanged disabled feature defaults, and
0015 remains not ready against 0016 source. No preserved database was upgraded.

This is non-destructive combined-schema compatibility, not a repeat of the
historical 24-case N19 deletion lab. Actual guarded cleanup, interruption recovery,
delegated maintenance/application role privileges, populated 0015 deployment
upgrade and production operator procedures still require separately authorized
acceptance on fresh resources. The test database role is the disposable PostgreSQL
initialization role, not proof of restricted deployment-role compatibility. All
browser, real-provider, full-duration and complete deployment limitations above
remain. N19 remains PARTIAL and is not candidate-wide deletion.
