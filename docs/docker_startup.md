# Isolated Docker synthetic startup

> **19 October release clarification:** Release checkpoint: office baseline startup evidence below does not establish complete application startup on a clean machine. Live media/STT/evaluation prerequisites remain outside the enabled baseline; current-source baseline rebuild passed at `b3c00db`; full-feature/clean-machine acceptance remains pending. See the [release checkpoint](release_candidate_checkpoint.md).

## Later release-candidate validation — 19 October 2026

Source `b3c00db` was built into a separate disposable Compose project. Empty
PostgreSQL was explicitly migrated through 0015. Seven integration checks passed:
private networking, schema identity, safe defaults, frontend/API/private-path
routing, disabled-caption WebSocket rejection, synthetic authentication and full
container recreation with database/session/file-marker persistence. Eight Docker
helper tests and 31 selected backend tests passed. TypeScript/Vite build passed.
Earlier office containers were unchanged. Subsequent commits through 5b6f172 are
documentation only; this does not claim a fresh-machine or full-feature test.
Private detailed logs remain outside Git. See the [home handover](office_home_handover.md).

## Separate service-integration test workflow

[Opt-in Docker F3–F6 tests](docker_f3_f6_tests.md) reproduce deterministic service
scenarios in fresh test-owned PostgreSQL. They do not extend the production
baseline or establish full-feature Docker acceptance.

## Implemented scope

Increment 1 adds three services without changing hiring logic:

```text
Browser → 127.0.0.1:5188 → nginx/frontend:8080 → backend:8000 → db:5432
              frontend-only edge bridge + internal service network
```

Only the frontend is published, on loopback. PostgreSQL and the backend have no
host port mapping. Backend and database use only `internal: true` networking and
cannot reach Internet providers. The frontend also has an edge bridge for Docker
Desktop's loopback port forwarding; it contains no provider credentials. The
loopback frontend is a production Vite build, not the Vite
development server. nginx proxies `/api/`, including WebSocket Upgrade headers,
to FastAPI. Other UI routes use the SPA fallback. Developer/private paths and
source maps are blocked. nginx is not a public HTTPS gateway.

The project name is **talenttrace-docker-demo**. Its new named volumes are
`talenttrace-docker-demo_postgres_data` and
`talenttrace-docker-demo_application_data`. No office/F4/intake volume, database,
private environment file or host data directory is referenced. Do not change the
project/volume configuration to point at existing demo data.

## Preflight

1. Verify a clean intended feature checkout and working Docker Linux engine.
2. Inspect existing containers/volumes and free disk space. Do not prune them.
3. Confirm port 5188 is free, or choose another port with the helper's `--port`.
4. If the named project/volumes already exist unexpectedly, identify their owner
   before proceeding. This guide does not authorize replacing them.
5. First builds require Internet downloads of pinned dependencies/base images.
   The CPU-only backend includes SentenceTransformers' PyTorch dependency and can
   occupy several GB. No model weights, CUDA libraries or Whisper models are
   downloaded by these Dockerfiles. Allow roughly 10 GB working headroom; actual
   measured usage is recorded below after verification.

## First setup — explicit migration, no automatic seeding

Use a terminal at the repository root (PowerShell or Linux shell):

```text
python docker/configure.py
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env config --quiet
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env build
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env up -d --wait db
```

The helper creates ignored `data/docker-demo.env`, refuses to overwrite it, and
prints no password. It generates a URL-safe random hex database password and a
loopback frontend port. Keep the file private; Unix mode is 0600, while Windows
privacy depends on the parent directory's NTFS ACL. Do not share resolved
`docker compose config` output or `docker inspect` environment output: these can
contain the password. The container receives only explicitly listed settings,
not the host `.env` or its Groq/SMTP/Google credentials.

Before migrating, verify this is the new disposable database:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env exec db psql -U talenttrace_demo -d talenttrace_docker_demo -c "SELECT current_database(), current_user;"
```

Expected database `talenttrace_docker_demo`, role `talenttrace_demo`. Check the
new project's volume ownership first. **Do not run the next command against any
existing office/F4/intake database.**

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env run --rm --no-deps backend python -m alembic upgrade head
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env up -d --wait --wait-timeout 180
```

Migration is an explicit operator action and the current office source reaches
`0017_booked_interview_email`, following `0016_submission_deletion` and
`0015_reviewer_confirmation`. Older 0015 startup evidence below is historical;
it is not verification of a new image/schema. Neither the entrypoint nor `up` migrates,
restores, seeds or creates a recruiter. If code introduces a future migration,
review/backup the disposable data and approve that migration separately.

Open http://127.0.0.1:5188/ (or the configured port). This origin must be used
consistently; switching to `localhost` is not part of the configured CORS contract.
Cookies retain existing HttpOnly/SameSite/mutation checks. Plain HTTP and
development cookies are limited to this loopback demo; do not expose it publicly.

Provision an account only by explicit operator action:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env exec backend python -m app.db.provision_recruiter
```

The existing command prompts for the synthetic email/password. It does not place
the password in command arguments. Sign in manually; an empty owned workspace
is expected. Nothing in this increment creates candidate data.

## Readiness and persistence

- PostgreSQL `pg_isready` gates backend startup.
- Backend readiness checks the existing `/api/v1/health` endpoint **and** that the
  database revision matches the code's single Alembic head. A live process with
  missing migrations is not ready. Diagnostics contain fixed safe messages only.
- Frontend starts after backend health passes and has its own HTTP check.
- Backend runs as UID 10001 and nginx as UID 101, with read-only root filesystems,
  writable temporary directories and dropped capabilities.
- Database records use the PostgreSQL named volume. Private application files use
  the separate application-data volume. Neither depends on a developer's host path.
- A volume outlives an individual container: ordinary stop, restart or `down`
  without `--volumes` does not remove it. Recreating containers therefore preserves
  the database and uploaded files. Volumes are persistence, **not backups**.
- First-time initialization/schema migration is separate from normal startup.

Subsequent normal startup:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env up -d --build --wait --wait-timeout 180
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env ps
```

Stop only this project, keeping all data:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env stop
```

Remove only this project's containers/network, keeping both named volumes:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env down
```

**Destructive reset is separate and never routine:** after explicit owner approval
and verification/backups, `down --volumes` would delete this project's named
volumes. No reset is performed by the implementation or verification workflow.
Never use global `docker system prune`, `volume prune`, or a shared volume name.
Keep the private env file: changing its password does not rotate credentials in
an already-initialized PostgreSQL volume.

## Synthetic verification

After explicit migration/startup, read-only deployment checks:

```text
python docker/verify.py --env-file data/docker-demo.env
```

An additional opt-in check provisions **two fictional recruiters and one job**, tests real
authentication/origin protection, writes a non-CV volume marker, and recreates
only this project's containers while retaining volumes:

```text
python docker/verify.py --env-file data/docker-demo.env --allow-synthetic-records
```

This is a data-changing disposable test, not part of startup. Each invocation
with that flag creates two new fictional accounts and one job; do not run repeatedly without
intending that. Credentials are generated in memory and never printed. No
provider, SMTP, publication, media or candidate-screening request is made.
The WebSocket test verifies proxy configuration and a real denied handshake to
disabled captions; it does **not** claim a media/caption session was established.

## Beginner-friendly explanation

- **Image:** packaged application and dependencies, built from a Dockerfile.
- **Container:** a running instance of an image. Recreating it replaces its own
  writable layer, not separately named volumes.
- **Compose:** describes the three services, their connections, health checks,
  configuration and storage in one version-controlled file.
- **Networks:** private service connections use DNS names `db` and `backend`;
  the frontend-only edge bridge enables the loopback port. The browser sees only
  that frontend, never a database/backend host port.
- **Environment variables:** supply local settings without committing secrets.
  Docker administrators can still inspect them; this is not a production vault.
- **Health checks:** prove readiness, not merely that a process exists.

For the viva: “The same Dockerfiles build the frontend and backend. Compose starts
the isolated database first and waits for readiness. Migrations are explicit.
Named volumes preserve records after container recreation, and optional external
actions remain disabled.”

## Limits

This increment demonstrates baseline startup, authentication, private networking
and persistence. It does not activate JD generation, screening, SMTP, Discord,
LiveKit, captions/storage, F5 or F6 confirmation. MCP is not necessary for startup
and no additional MCP service or private MCP configuration is included. Models
and approved policy records are not seeded. Optional STT packages/models are not
installed. The backend's internal network deliberately prevents provider access.

Base images are digest-pinned; existing direct Python dependencies and the pnpm
lockfile are retained. CPU PyTorch and pnpm are pinned for this build. Python
transitive dependencies are not fully hash-locked, OS image vulnerability review
and multi-architecture testing remain separate work, and cold builds need network
access. N21 clean-machine/full-feature acceptance requires another clean machine
or equivalent fresh environment; a successful office build is not that claim.

### Verification evidence

**Verified 19 October 2026**, Windows Docker Desktop Linux engine 29.8.1,
on `feature/docker-reproducible-startup` based on `e059709`. This is an office
verification, **not a second clean-machine or complete N21 acceptance claim**.

| Check | Actual result |
| --- | --- |
| Compose validation / image builds | Passed; backend and frontend built, followed by a successful cached build with digest-pinned bases. |
| No implicit schema mutation | New DB had zero public tables; API liveness passed while backend readiness correctly failed. No automatic migration/seed occurred. |
| Explicit migration | Only `talenttrace_docker_demo` migrated through `0015_reviewer_confirmation`; pgvector extension available. |
| HTTP / API | Frontend and candidate SPA route returned 200; API health returned 200 through nginx; unauthenticated account returned 401; private/developer/source-map routes returned 404. |
| WebSocket routing | Actual Upgrade request reached disabled caption handling and returned 403; nginx configuration has HTTP/1.1 and both Upgrade headers. No caption/media session was activated. |
| Authentication | Existing provisioning CLI created a synthetic fixture; valid login/session, HttpOnly/SameSite cookie, rejected foreign Origin, owned empty workspace and logout passed. |
| Recreation persistence | All three containers removed/recreated without deleting volumes; database identity/revision/account, existing session and private-file marker survived. |
| Isolation | Only frontend port `127.0.0.1:5188` published. DB/backend attached only to internal network. All seven original containers retained exact state, start/finish timestamps and mount identities. |
| Safe optional startup | Email, LiveKit, transcript saving, inference and confirmation activation disabled; no provider keys/private office config copied. CPU-only torch confirmed; no Hugging Face model cache created. |
| Regression tests | 26 focused existing backend checks + 6 readiness unit checks + 2 verifier regression checks passed; 231 frontend tests passed, zero failures/skips in these runs. |
| Production build | TypeScript/Vite passed in the image. Existing >500 kB LiveKit chunk warning remains. |
| Integration verifier | Seven grouped end-to-end checks passed, including container recreation. |

Two issues were discovered and corrected before the final passing run:

1. Docker Desktop did not expose the configured port on an internal-only network.
   A frontend-only edge bridge fixed forwarding while backend/DB stayed private.
2. Windows text pipes added CR to Linux `getpass` test input. The verifier now
   passes UTF-8 bytes, with a regression test. Application password/authentication
   semantics were not changed. One earlier diagnostic account remains alongside
   the final successful test account, **only in the new disposable database**.

Final disposable counts: two fictional test recruiters, zero jobs, scores,
interviews and email attempts. No existing demo database was started or migrated.
The test accounts' generated credentials were not printed or retained in source;
provision a personal synthetic demo login explicitly using the documented command.

Disk measurement: backend image approximately **2.32 GB**, frontend **74.9 MB**;
existing pgvector image **627 MB** reused. Build cache reports **2.93 GB**, with
shared layers that must not be added blindly to image sizes. Windows C: free
space decreased approximately **3.8 GB** during the work and remained about
**97.1 GB** free. No old images, volumes or build caches were pruned.

Re-run offline guard tests with the existing backend Python dependencies:

```text
python docker/test_readiness.py
python docker/test_verifier.py
```

Keep `data/docker-verification/` and `data/docker-demo.env` private and ignored.
Do not treat a successful small synthetic authentication test as full F1–F6,
production security, long WebSocket/media, or clean-machine acceptance.


## Current release audit — 28 October 2026

See [current Task 8 evidence and BID matrix](task8_release_audit_20261028.md).
The verifier now accepts `--project <explicit-new-project>` and compares the
database revision to the image's single Alembic head rather than historical 0015.
Use the same `-p` project for configuration, build, migration, startup, verification
and stop. A project name does not authorize using existing volumes. Verify unused
project/volume identities first; `--allow-synthetic-records` creates two fictional
accounts and one job and recreates only that explicitly selected project. It checks
job/reference/revision and authenticated-session persistence, foreign-owner denial
and unavailable-provider rejection. No inference is requested with valid keys.
