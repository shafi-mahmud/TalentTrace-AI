# Office → Linux Mint continuation — 25 October 2026

Prepared from local code and retained evidence. Commands below are a reviewed
runbook, **not commands executed by this handover task**. Home hardware, checkout,
installed packages, credentials and models were not inspected. Keep the original
home checkout and all existing volumes/configuration intact.

## Source checkpoint and publication gate

| Ref / worktree role | Verified local HEAD | State / action |
| --- | --- | --- |
| develop / develop-integration | `cba35ab376ade05afb5a896bb64fba3bed5172c5` | Clean; recommended first publication after owner approval |
| origin/develop, independently read from GitHub | `49961fc74c48c38e0cb16c5e12b10ba6c2d7593d` | Ancestor of local develop; ten commits behind |
| local and remote main | `171937ef51310094371466f51e2649a5e9d710a9` | Unchanged; no action |
| feature/f3-cloud-acceptance-docs | `0ae4083c5ccf007f078e14526a63d48c09030919` | Clean; two documentation files beyond develop; publish separately only after approval |
| feature/trainer-feature-status | `d68d7cf4807d2c0ebe23c20ba4d1448873f9daf7` | Clean; trainer audit only beyond develop; publish separately only after approval |
| feature/recruiter-final-readiness-20261025 | `cba35ab376ade05afb5a896bb64fba3bed5172c5` | Clean tracked state; useful new test/demo artifacts are ignored and machine-local |
| feature/docker-livekit-interview | `aa97342630b309387fda6d983b2c5aa8c296b50e` | Clean; experimental self-hosted profile remains separate, with unresolved failures |
| feature/f11-browser-acceptance | `2446376cab0a2e2f26419097e4f1e1884ae01396` | Clean, frozen partial acceptance; do not merge for the home move |
| original feature/recruiter-job-ownership | `80dc5c913832f33341008e0e01c3af52d8523388` | Preserve modified MCP config and untracked office status note; do not stage/restore them |

All 41 pre-existing worktrees were checked: only the original checkout was dirty.
Its config difference is blank-line-only. This new documentation worktree is an
additional, intentionally uncommitted review checkpoint based on develop.

Ten outgoing commits, preserving the existing merge/history:
`2660232`, `67e88ae`, `b67dde1`, `aeea7ee`, `9ad003a`, `1d91de8`,
`d1a8a32`, `ac830ff`, `c9912aa`, `cba35ab`.
They contain Home/JD, scheduling review, notifications/dashboard, reviewed
appointment confirmation/contact binding, connected tests and imported screening.
No essential additional unmerged application feature was identified. Older
notification/external-intake branch names are not evidence that their later
integrated functionality is missing. Optional LinkedIn branch `ccb19e5` stays
separate; do not integrate it or the Docker/F11 experiments for synchronization.

Targeted outgoing review covered 70 source/test/documentation files and whitespace
checks. No private artifact paths or high-confidence JWT/provider-key/private
invitation payloads were found; added email domains were synthetic. This is a
bounded review, not a guarantee from an exhaustive data scanner. Ignored private
directories were not copied into the diff. Both acceptance/audit documentation
refs are currently absent on GitHub; local branch existence is not publication.

**Do not push in response to this runbook alone.** After explicit owner approval,
recheck exact clean local develop, read/fetch remote develop safely, confirm remote
still equals the recorded SHA and is an ancestor of local develop, then perform
only the approved ordinary non-force push. Stop on any changed/diverged ref.
Develop is published first; the two documentation branches remain separate and
can be published under distinct approval. This handover needs review/commit
authorization before it can itself be published. No merge into main is proposed.

## New home checkout; never overwrite the old one

Proceed only after approved develop publication. Inspect the existing home
checkout read-only with `git status --short` / `git rev-parse HEAD`; do not pull
over local changes or reset it. Choose an unused destination and authenticate
through normal private Git access, never a token embedded in a URL.

```bash
# Set this to the existing private repository URL without embedded credentials.
repo_url='https://github.com/shafi-mahmud/TalentTrace-AI.git'
destination=TalentTrace-AI-home-20261025
test ! -e "$destination" || { echo 'STOP: destination exists'; exit 1; }
git clone --branch develop --single-branch "$repo_url" "$destination"
cd "$destination"
expected=cba35ab376ade05afb5a896bb64fba3bed5172c5
test "$(git rev-parse HEAD)" = "$expected" || { echo 'STOP: unexpected source'; exit 1; }
test -z "$(git status --porcelain)" || { echo 'STOP: dirty new checkout'; exit 1; }
git switch -c feature/home-readiness-20261025
```

If publication was not approved/completed or origin advanced, stop rather than
changing `expected` by guesswork. Read separately published documentation with
an explicit fetch/show or separate documentation worktree; do not merge it into
the implementation merely to read it.

## Dependencies and portability

Dockerfiles pin Python 3.12.10, Node 24.19.0, pnpm 11.25.0, PostgreSQL 17 /
pgvector 0.8.6 and nginx 1.28.0, including image digests. Prefer these contracts
over an arbitrary host upgrade. A cold build requires ordinary package/image
downloads and disk/RAM headroom; it does not download speech models. Source
presence is not proof that dependencies are cached on the home laptop.

Do not copy Windows virtual environments, node_modules/junctions, private .env,
databases, cookies or invitations. Recreate private configuration locally. Linux
paths/imports are case-sensitive; a frontend build checks the current imports.
Use Bash commands here, not PowerShell `$env:` syntax or D-drive paths.

Optional host work needs a new Linux venv and the locked frontend dependencies:

```bash
python3 --version                  # target Python 3.12; Docker supplies exact pin
node --version                    # target Docker-pinned Node 24.19.0
pnpm --version                    # target 11.25.0
docker compose version            # Compose v2
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.14.1+cpu
python -m pip install -r backend/requirements-dev.txt
python -m pip check
(cd frontend && pnpm install --frozen-lockfile)
```

Dependency installation is an explicit setup operation, not an offline smoke
test. Stop on unsupported wheels/CPU libraries instead of changing package pins.
Optional STT uses `backend/requirements-stt.txt` (Faster-Whisper 1.2.1 and
websockets 16.1.1); the base Docker image does not install that extra or model
weights. Windows LiveKit.exe cannot run on Linux. Cloud transport needs no local
LiveKit binary; a future self-hosted Linux proof needs its own official binary
or container and separate reviewed configuration, not the failed office profile.

## New isolated Docker baseline (media/providers disabled)

Use an unused project and loopback HTTP port. The examples use 5288 to avoid
office/protected defaults; if either identity is occupied, stop and choose a
consistent new pair before generating configuration.

```bash
project=tt-home-20261025
env_file=data/docker-demo.env
umask 077
test -z "$(docker ps -aq --filter label=com.docker.compose.project="$project")" || { echo 'STOP: project exists'; exit 1; }
test -z "$(docker volume ls -q --filter label=com.docker.compose.project="$project")" || { echo 'STOP: project volume exists'; exit 1; }
for volume in "${project}_postgres_data" "${project}_application_data"; do
  if docker volume inspect "$volume" >/dev/null 2>&1; then echo 'STOP: named volume already exists'; exit 1; fi
done
for network in "${project}_private" "${project}_edge"; do
  if docker network inspect "$network" >/dev/null 2>&1; then echo 'STOP: named network already exists'; exit 1; fi
done
ss -ltn '( sport = :5288 )'         # expect header only; stop if a listener exists
df -h .
free -h
python3 docker/configure.py --port 5288
docker compose -p "$project" --env-file "$env_file" config --quiet
docker compose -p "$project" --env-file "$env_file" build
docker compose -p "$project" --env-file "$env_file" up -d --wait db
docker compose -p "$project" --env-file "$env_file" exec -T db \
  psql -U talenttrace_demo -d talenttrace_docker_demo -Atc \
  "SELECT current_database(),current_user,(SELECT count(*) FROM information_schema.tables WHERE table_schema='public');"
```

Expected identity is database `talenttrace_docker_demo`, role `talenttrace_demo`
and zero public tables. Verify the new project's container/volume labels too.
There are no host database ports, host .env mounts or external volumes in base
Compose. Do not print resolved Compose configuration/environment. Stop if the
database is nonempty or ownership is ambiguous; never migrate a preserved DB.

Only after those checks pass, migrate the new database explicitly:

```bash
docker compose -p "$project" --env-file "$env_file" run --rm --no-deps backend python -m alembic heads
# Exactly: 0017_booked_interview_email (head)
docker compose -p "$project" --env-file "$env_file" run --rm --no-deps backend python -m alembic upgrade head
docker compose -p "$project" --env-file "$env_file" exec -T db \
  psql -U talenttrace_demo -d talenttrace_docker_demo -Atc 'SELECT version_num FROM alembic_version;'
docker compose -p "$project" --env-file "$env_file" up -d --wait --wait-timeout 180
docker compose -p "$project" --env-file "$env_file" exec -T backend python /app/docker/backend_ready.py
curl --fail http://127.0.0.1:5288/api/v1/health
```

Expected: one revision `0017_booked_interview_email`, `ready`, HTTP 200. Readiness
rejects 0015/0016; it does not migrate them. Current Docker F3–F6 test runner
already reviews/verifies 0017. Old documentation expecting 0015 is historical.
No recruiter is automatically provisioned. When separately authorized, use the
existing `app.db.provision_recruiter` CLI on this new project only; do not invoke
the verifier's synthetic-record/recreation mode merely to inspect readiness.
`docker/verify.py` otherwise hardcodes the office project. Prefer the checks above;
its read-only mode still performs a local disabled-caption WebSocket probe.

## Focused offline smoke and STT availability

After dependency setup, run only selected model-independent contracts:

```bash
(cd backend && env -u DATABASE_URL -u LANGGRAPH_CHECKPOINT_DATABASE_URL -u GROQ_API_KEY -u ASSEMBLYAI_API_KEY -u LIVEKIT_API_KEY -u LIVEKIT_API_SECRET -u LIVEKIT_URL HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 python -B -m pytest -p no:cacheprovider tests/test_health.py tests/test_livekit_interview.py -q)
(cd frontend && env -u VITE_API_BASE_URL node --experimental-strip-types --test tests/livekitInterview.test.ts tests/syntheticInterviewMedia.test.ts tests/recruiterHome.test.ts)
(cd frontend && env -u VITE_API_BASE_URL pnpm build)
```

Expected: selected cases pass and build succeeds, with the known possible large
LiveKit bundle warning. Record actual home counts; do not copy office counts as
new results. Do not enable opt-in PostgreSQL/destructive/provider tests here.
The new clone must have no root .env; these commands also remove inherited
database/provider settings so another checkout's environment is not reused.

For optional STT, first supply an owner-approved local model directory outside
Git and install optional pinned dependencies explicitly if approved. Check files
and package metadata without constructing WhisperModel or contacting a provider:

```bash
model_dir="$HOME/.local/share/talenttrace-models/tiny.en"
python - "$model_dir" <<'PY'
import importlib.metadata as m
from pathlib import Path
import sys
root = Path(sys.argv[1])
print('faster-whisper', m.version('faster-whisper'))
for name in ('model.bin', 'config.json', 'tokenizer.json', 'vocabulary.txt'):
    print(name, (root / name).is_file())
PY
```

Expected: version 1.2.1 and all required files present. Missing assets mean STOP,
not automatic download. Validate native CPU/OpenMP/CTranslate2/PyAV availability
in a separate local-only model-start preflight; presence alone is not recognition
acceptance. The worker already uses sys.executable/Path, CPU int8 and
local_files_only with offline settings. Do not increase its bounded waits as a
substitute for diagnosing missing/incompatible dependencies.

## Cloud/F4 gates and office evidence

Baseline Compose deliberately disables LiveKit, captions/storage, evaluation,
copilot and email; its backend has only an internal network. It is not a full
Cloud/STT runtime. Merely flipping flags would omit optional packages/models,
external administrative connectivity and privacy/resource preflight.

Before a later authorized Cloud/F4 proof, prepare a Linux-native isolated profile:
server-side Cloud credentials from private local configuration, development
synthetic-media opt-in, supported Cloud wss endpoint, fresh fictional booking and
unclaimed invitation, local model, same-origin caption WebSocket proxy and fresh
independent browser profiles. Check included free allowance and processing
authorization with the owner first; make no Cloud call in this setup runbook.
nginx already forwards WebSocket Upgrade/Host/Origin. Use 127.0.0.1 consistently;
localhost is a different origin, and cookies are host-scoped, not port-isolated.

Office-only ignored launchers hardcode Windows paths/shells and cannot be run
unchanged on Linux. Do not transfer claimed/expired invitations or private DBs as
recovery shortcuts. Approved generated WAV source fixtures are already tracked;
model weights/private synthetic outputs are separate local assets, not Git data.
Transfer only reviewed sanitized text/checksums when needed, never bulk private
directories. No automatic model or credential transfer is part of this handover.

Confirmed office evidence: current Cloud F3 bounded synthetic media PASS, both
11-record journals and owner-observed remote media; self-hosted root cause still
UNKNOWN. F4's prepared window expired at 13:50:51 on 25 October without a trial.
Fresh recruiter demo passed 18 setup API and six local HTTP checks with model/
SMTP doubles; authenticated desktop/mobile acceptance remains pending. Its
14:22:14 cutoff has passed: the owned demo DB is exited and relevant ports were
inactive during this audit. Completed F3 reports/journals and private artifacts
remain preserved. F11 is frozen PARTIAL, with no simultaneous active-suggestion
candidate exclusion/terminal expiry proof. Do not re-label these as home tests.

## Parallel plan through the reported 26 October evaluation

| Group / branch | Dependencies and acceptance | Conflict boundary |
| --- | --- | --- |
| P1 short F3→F4 / proposed `feature/f3-f4-short-acceptance` | Published source, Linux local model, fresh approved synthetic booking/profile/consents. Both WAVs traverse real track/AudioWorklet/STT; correct roles/times, drain, saved retrieval after reload. | Caption/media/storage code; keep F11 frozen while accepting this path. |
| P1 recruiter visual / existing `feature/recruiter-final-readiness-20261025` source at cba | Fresh Linux-safe fake-provider/SMTP demo and isolated profile. Desktop/mobile create/refine/reference/intake/screen/notifications/book/email/reload. | App/Home/CvIntake/scheduling/email/CSS if a confirmed defect appears; separate branch/resources from F4. |
| P1 source/evidence / separate 0ae4083 and d68d7cf docs | Publish develop first with approval; review docs independently. Current Cloud evidence and six-implemented/five-partial/three-missing trainer matrix. | Documentation only; one owner for handover edits. |
| P2 F11 / frozen branch 2446376 | Explicit resume decision after F4. Fresh active recruiter suggestion plus overlapping candidate API/DOM exclusion and one terminal behavior. | Live-caption adapter/role projection/consent; do not overlap F4 lifecycle edits. |
| P2 publishing/provider scope / proposed documentation branch | Clarify Discord-only explicit review versus requested chat multi-platform; task-specific provider configuration. No posting to establish configuration. | Chat/MCP/settings; LinkedIn ccb19e5 stays separate. |
| P3 defer | Biometrics, proctoring, screen sharing, broad provider selector and long-duration/multi-room captions need separate scope/privacy/resource acceptance. | High-risk cross-cutting changes; do not treat trainer suggestions as newly proven BID mandates. |

## Troubleshooting, stopping and returning to office

Stop on a SHA mismatch, dirty checkout, existing project/volume, nonempty database,
multiple/wrong migration heads, failed readiness, wrong origin or unavailable
model. Do not repair by resetting Git, changing stored booking times, lifting
resource bounds, reusing invitations or migrating another database. Collect only
sanitized categories/statuses; raw Docker logs/configuration may contain secrets.

```bash
docker compose -p "$project" --env-file "$env_file" stop
git status --short
git rev-parse HEAD
```

Retain env/volumes and evidence. No prune, volume deletion or hard reset. On home,
work in a clearly named feature branch and record its base/full HEAD, focused
checks, dirty files and owned runtime state before leaving. Publish only with
explicit approval. On office, inspect home branch ancestry after an approved
fetch; use a new worktree or reviewed integration, never force-update a checked-out
branch. Keep office develop and the original dirty config intact until the owner
reviews the combined state. No concurrent edits to the same feature branch on
both laptops, and no direct copy-over of a working tree or database.
