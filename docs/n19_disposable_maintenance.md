# N19 isolated maintenance deployment

This is the supported environment for destructive synthetic acceptance, not a
command for existing Windows/F11/demo databases or volumes. It uses existing
local images only, an internal Docker network, a new PostgreSQL volume and a new
CV volume. No database port is published. Resources have unique `tt-n19-lab-*`
names and ownership labels. Never attach preserved data to this lab.

## Establish and prove the boundary

From the repository root, using the existing host Python environment:

```text
python -B docker/n19_lab.py init --state data/n19-maintenance/lab.json --confirm-new-disposable
python -B docker/n19_controls_acceptance.py data/n19-maintenance/lab.json
```

The first command refuses an existing state file and never pulls an image. The
private ignored state file contains generated lab-only credentials. Preserve it
privately for recovery; do not commit it. Partial provisioning leaves the state
file for inspection, rather than guessing whether provisioning should be retried.

The second command is a synthetic control test, not candidate deletion. It proves
an actual application database connection and storage write work initially, an
active connection blocks entry, application login/storage access are denied
afterward, an unexpected CV-volume mount blocks inspection, and the maintenance
block survives restarting the newly created worker only.

There are separate non-superuser roles: `n19_application` and
`n19_maintenance`. The latter has delegated role-management privileges and owns
the lab database. PostgreSQL superuser credentials are provisioning-only. During
maintenance the application role is `NOLOGIN`, no other target-database client
or prepared transaction is permitted, and CV storage is owned by maintenance
UID 10002 with root mode 0700. UID 10001 is the application identity.

The host controller checks every container, including stopped containers, for
unexpected mounts of this specific CV volume. It rejects running application
UID processes inside the maintenance container before transferring ownership:
open file descriptors would not be revoked by chmod. Links/special files and
hard-linked files prevent storage ownership transfer. No global process killing,
firewall changes or existing database permissions are used.

**Threat model:** Docker-daemon/host administrators and the operator are trusted.
They can bypass container isolation; this is not protection against a malicious
administrator. All ordinary application writers must use the application role/UID
and deployment-managed mounts. Undocumented credentials, storage mounts or other
administrative writers invalidate the procedure. An advisory lock alone is not
the access boundary.

`python -B docker/n19_lab.py check --state data/n19-maintenance/lab.json` rechecks
the deployed controls. Failed maintenance entry may leave `NOLOGIN` in place;
never automatically restore access on failure. This is intentional fail-closed
behavior. No application service exists in this synthetic lab to auto-restart.

The existing inventory/preflight remain read-only previews. Their permanently
negative generic readiness result is not overridden: the isolated controller
provides separate, deployment-specific enforcement evidence.

Existing LiveKit, F11, SMTP, inference and public-network services are not part
of this lab. Cached LiveKit tokens for real interviews are not invalidated by
these controls. External copies, backups and WAL are not erased by local cleanup.

## Final-attempt checkpoint — PARTIAL

Implemented and exercised: isolated provisioning through migration 0015,
non-superuser application/maintenance roles, actual active-client refusal,
application database admission denial, application storage denial, unexpected
volume-mount refusal, and maintenance state surviving a worker restart.
The deployed `check` command also passed after the control test. Only the newly
created lab worker was restarted; preserved demo services were not targeted.
Focused validation: 37 tests passed with `N19_TEST_PG=1` from `backend/`
(`test_candidate_inventory`, `test_deletion_preflight`, `test_interview_access`,
`test_livekit_interview`); syntax and `git diff --check` passed. An initial pytest
invocation from the repository root failed collection because `app` was not on
the import path; rerunning from the documented backend working directory passed.

Not implemented: destructive candidate CLI, deletion journal/tombstones,
import suppression, dependency-ordered database cleanup, file cleanup, interrupted
cleanup recovery, and verified candidate-data absence. No candidate deletion was
executed. The unfinished draft was removed before closure; no new migration or
importer behavior is included in this increment. N19 remains incomplete.

The lab remains blocked in maintenance mode. Do not restore application access
or attach existing data. The next increment must implement and test the journal,
conservative association checks, selective deletion and importer suppression
inside this lab before claiming deletion acceptance. Generic inventory/preflight
output remains a preview, never execution authorization.
