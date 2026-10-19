# Office → Linux Mint home handover — 19 October 2026

## Start here

Repository: `shafi-mahmud/TalentTrace-AI` on private GitHub.
Start from `feature/pre-viva-release-docs`, published at
`5b6f1729e0ec90fe65af0057e24ac6f2b8554d16`. This is a source checkpoint, not
full BID acceptance. A later local handover-docs commit requires separate push
approval. Do not assume it is already on GitHub.

Use a new folder; preserve any existing home checkout, environment and database:

```bash
git clone --branch feature/pre-viva-release-docs https://github.com/shafi-mahmud/TalentTrace-AI.git TalentTrace-AI-pre-viva-20261020
cd TalentTrace-AI-pre-viva-20261020
repo_dir="$(pwd)"
git status --short
git rev-parse HEAD
```

Expected initial HEAD is the full SHA above unless a newer documentation push is
explicitly approved. Authenticate through your normal private GitHub access; never
put a token in the remote URL. Do not reset a different checkout to make it match.

## Prerequisites and isolated baseline

Docker Linux engine + Compose v2 and Python 3 are required. Python 3.12 is the tested
host version; the private-config helper documents Python 3.10+. Host Node is needed
only for frontend development/tests: tested Node 24.19 and pnpm 11.25. Dockerfiles
pin Python 3.12.10, Node 24.19, pnpm 11.25, PostgreSQL 17/pgvector and nginx images.
Allow several GB of disk/build-cache headroom and check free RAM first. Office
images were roughly 2.32 GB backend and 75 MB frontend, plus shared layers/pgvector;
a home cold build requires dependency downloads. No STT model is downloaded by
the baseline. A Windows virtual environment or LiveKit.exe is not usable on Linux.

Inspect existing resources before choosing the new project name/port. If either
already exists, stop and select a different name/port consistently below:

```bash
docker info
docker compose version
docker ps -a --format '{{.Names}} {{.Ports}}'
docker volume ls
free -h
df -h .
python3 docker/configure.py --port 5188
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env config --quiet
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env build
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env up -d --wait db
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env exec -T db psql -U talenttrace_demo -d talenttrace_docker_demo -Atc "SELECT current_database(),current_user,(SELECT count(*) FROM information_schema.tables WHERE table_schema='public');"
```

Confirm the new database identity and zero public tables before initial migration.
Do not reuse any existing volume or restore an office database:

```bash
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env run --rm --no-deps backend python -m alembic upgrade head
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env up -d --wait --wait-timeout 180
curl --fail http://127.0.0.1:5188/api/v1/health
```

Expected revision: `0015_reviewer_confirmation`. The helper refuses to overwrite
its generated ignored environment file. Do not print resolved Compose environment
or Docker inspect environment fields. `.env.example` supplies placeholder contracts;
no office secrets, OAuth credentials or database passwords are required for baseline
startup. Use the normal explicit recruiter provisioning CLI when needed.

## Tests, authentication and persistence

The existing verifier hardcodes the office default project. Override its module
variable for this new home project; do not run its unmodified destructive smoke
command against another project's volumes. The following explicitly creates one
fictional recruiter and recreates only `talenttrace-home-viva` containers while
retaining its volumes; no model, email, publishing or media operation is requested:

```bash
python3 - <<'PYCODE'
from pathlib import Path
import sys
sys.path.insert(0, 'docker')
import verify
verify.PROJECT = 'talenttrace-home-viva'
verify.main(Path('data/docker-demo.env').resolve(), True)
PYCODE
```

For optional host regression work, use a new virtual environment and the pinned
requirements. CPU-only torch is the same choice as the Dockerfile. These commands
install dependencies but do not download a speech model or run inference:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu
python -m pip install -r backend/requirements-dev.txt
python -B docker/test_readiness.py
python -B docker/test_verifier.py
(cd backend && HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -B -m pytest -p no:cacheprovider tests/test_health.py tests/test_database_foundation.py tests/test_recruiter_records.py -q)
(cd frontend && pnpm install --frozen-lockfile && pnpm test && pnpm build)
```

Do not enable live-test environment gates without reviewing their disposable DB/
model requirements. Office pre-publication evidence:360 backend passes, 62 gated
skips; 242 frontend passes; typecheck/build passed. Separate N21 task: 31 backend
passes, 8 Docker helper passes, 7 integration groups. These are overlapping scoped
runs, not a newly executed home/full-suite result. Models and enabled media/F5/F11
are absent from baseline Compose; healthy containers do not establish full N21.

## Feature checkpoint and October 20–21 priorities

- F1/F2 implemented with source evidence; N1 real 20-input attempt took 449.09 s:
  20 parsed, 19 decisions, 15 eligible, 4 excluded, 4 numeric scores, 11 uncertain,
  one 429 failure. Evidence handling—not a manual retry—is the next offline review.
- F3 two-party media and F4 short saved capture passed controlled demonstrations.
  Full-duration speech/network acceptance and cached/refreshed self-hosted LiveKit
  JWT revocation remain unresolved. Fresh rooms do not revoke old tokens.
- F5 controlled actual capture→Groq→grounded durable result passed; broader pairing,
  language/corpus and natural-interview acceptance remains limited.
- F6 synthetic reviewer confirmation/report/comparison is implemented and verified
  in its documented scope. Do not invent absent interview evidence.
- F11 logic/delivery/live hook automated tests passed; physical speech→suggestion
  acceptance remains pending. See [rationale and assistance disclosure](f11_innovation_rationale_draft.md)
  and [BID matrix](release_traceability.md). Authorship compliance is not certified.
- N19 remains PARTIAL: no actual deletion/journal/tombstones/re-import suppression.
  Four commits on separate `feature/n19-candidate-deletion` at `4d37ba5` are not
  included in release. Notifications `4b25a27` and LinkedIn `ccb19e5` are published
  separately, not integrated. External intake `112c07b` has no matching published
  branch at handover; do not assume that full collector is available remotely.

October 20: verify the home checkout and baseline without importing office data;
review the existing evidence and F11 prerequisites; confirm source/backups are
recoverable. Investigate N1 uncertainty offline before proposing new inference.
October 21: one separately authorized bounded physical F11 test if prerequisites
are sound; otherwise retain PARTIAL. Prepare the viva explanation and reviewed
integration proposal. N19 actual cleanup needs a separate safe increment, not a
rushed destructive change. Defer optional integration and unrelated new features.
No new provider run, merge or deployment is authorized by this handover document.

## Local-only assets and safe transfer

GitHub contains source/history, not office databases, model caches, private fixtures,
benchmark responses/logs, credentials, invitations, browser profiles or recordings.
On the office machine the ignored handover folder is `data/office-handover/`.
Copy its verified `n19-reviewed.bundle`, checksum, worktree inventory and original
MCP whitespace patch via secure private storage if needed. Do not commit it.
The N19 bundle includes only four audited commits and requires ancestor 176ba82,
which the published release already contains. In the home clone:

```bash
# Set handoff_dir to the private folder you actually transferred.
cd "$handoff_dir"
sha256sum -c n19-reviewed.bundle.sha256
# Return to the home repository before the Git commands below.
cd "$repo_dir"
git bundle verify "$handoff_dir/n19-reviewed.bundle"
git branch --list feature/n19-candidate-deletion
# Only if that local branch does not already exist:
git fetch "$handoff_dir/n19-reviewed.bundle" refs/heads/feature/n19-candidate-deletion:refs/heads/feature/n19-candidate-deletion
```

Alternatively, after a separately approved N19 push, fetch its private remote branch
and verify the full expected tip; do not merge it into release by default. The
Windows maintenance scripts must be reviewed for Linux compatibility before use.

For evidence transfer, keep private N1/N21/publication-gate reports separate from
source; encrypt sensitive configurations/backups and transfer only what is needed.
Recreate home environment secrets privately. Do not transfer claimed invitations or
browser cookies as a session-recovery mechanism. Existing tiny.en/base.en folders
and local embedding caches require separate approved transfer or installation;
copying Git cannot provide them. The BID/WBS originals are also separate local
artifacts; use their authoritative versions rather than invented replacements.

## Failed setup recovery

Stop only the new home project with the command below; keep volumes/env and inspect
logs privately. Do not delete volumes, change schema manually, rerun an uncertain
provider operation or point at office/home preserved databases to bypass failure:

```bash
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env stop
```

Restart the same project with `up -d --wait`; do not recreate its environment file.
A failed migration requires inspecting its actual revision before deciding recovery.
No `down -v`, prune, reset, force push or database restore belongs in this procedure.
