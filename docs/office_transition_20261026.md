# Home → office continuation — 26 October 2026

Repository: `shafi-mahmud/TalentTrace-AI`. GitHub privacy was checked as **private**
during this handover. This is a source/documentation transfer, not environment,
provider, database, biometric-policy or trainer acceptance. No runtime was activated.

## Branches and exact ancestry

| Branch | Verified implementation tip before this handover |
| --- | --- |
| develop | `7c2725e566199f85c194ca9c4eef39ea2934f5f4` |
| feature/trainer-gap-closure-1 | `579eeca228c21259f23f4bf4cb0899940e6da7b4` |
| feature/face-verification-viva | `a3d0e2d91246ec9ba3f816b0d7a25d1bfdf30679` |

This documentation commit becomes the new face-branch tip; its exact SHA is recorded
by Git/the publication report, not recursively embedded in its own contents.
Both earlier branch tips remain unchanged. The office should use
**`origin/feature/face-verification-viva`** for all completed source, keeping optional
features disabled until explicitly prepared. Do not merge this branch into develop
merely to continue studying or testing.

History, in order:

- Develop includes analytics `cf647c5`, publishing `73513d5`, their normal merges
  `26b6ca2`/`3acede9`, integration `fd6a320`, F11 `e947bdc`, access `2cd17b9`,
  screen sharing `17775d6`, JD provider selection `d2cd8d4`, integrity indicators
  `6d9ce5e`, and final integration documentation `7c2725e`.
- Gap closure descends directly from develop: CV provider selection `5127f7f`,
  then opt-in Telegram destination `579eeca`.
- Face branch descends from gap closure: numeric lifecycle prototype `8c7ec8b`,
  real CPU readiness `f0a859b`, bounded real comparisons `fba18db`, and encrypted
  synthetic enrollment/viva workflow `a3d0e2d`, followed by this handover commit.
- Unapproved `feature/trainer-ui-finalization` was excluded from the integrated
  history. N19 and unrelated experimental branches were not merged. Main is not
  modified by this handover; biometric code is **not** merged into develop.

## Implemented features and limits

| Area | Implemented source | Remaining acceptance boundary |
| --- | --- | --- |
| Recruiter workflow | Owned jobs, Job Reference/revision, JD refinement, reviewed criteria, trusted intake/screening, scheduling | Existing synthetic evidence is not a complete physical/provider walkthrough |
| Dashboard analytics | Job-scoped counts, source reconciliation, New/Viewed filtering and explicit displayed-set acknowledgement | No invented predictive/date/outcome analytics or universal person deduplication |
| AI model choice | Independent JD/CV selectors; fixed allowlisted Ollama models or configured Groq; CV extraction and matching use the selected provider; explicit external-CV transfer confirmation; no local→cloud fallback | Local-model accuracy/readiness unmeasured. Legacy JD API behavior remains documented; local host endpoints need Windows/runtime configuration |
| Publishing | Saved-job preview, explicit destinations/confirmation, per-destination receipts; Discord MCP and disabled-by-default Telegram channel Bot API; LinkedIn manual | Automatic delivery mocked, not newly live-tested. Duplicate fencing is process-local, not durable/global. No automatic LinkedIn API claim |
| Candidate access | One-use invitations, hashed scoped sessions, ownership/current criteria/windows, revocation checks | Invitation possession is not identity proof; do not reuse/rotate invitations casually |
| F3/F4/F11 | Scoped LiveKit media, bounded local captions with separate storage consent, trusted events → model-free LangGraph → recruiter-only optional suggestions/dismiss | Fresh home/office Cloud acceptance and visible browser suggestion still require controlled acceptance; no human cloud-STT accuracy claim |
| Concurrent interviews | Independent room/auth/state isolation, safe rejection of a second caption room | **One caption room per backend process**; multi-room concurrent F4/live F11 is not implemented |
| Screen/attention | Explicit screen sharing; optional disclosed tab/page-fullscreen indicators | Real browser/Cloud/native picker acceptance incomplete; no recording, surveillance or cheating proof |
| Synthetic face workflow | Actual CPU YuNet/SFace, protected synthetic-reference persistence, separate candidate consent, recruiter-authorized later 1:1 review, withdrawal/deletion/expiry | Real biometrics remain impossible through the prototype API; approved policy, storage/key/backup governance, source-deletion integration, evaluation, liveness and real on-site authority remain blockers |

The existing self-hosted LiveKit cached-JWT revocation limitation is not claimed
resolved. N1 full 20-CV benchmark, N19 whole-candidate deletion and N21 full-feature
Docker deployment acceptance remain partial. Healthy baseline containers do not
establish full N21. The frozen/unapproved branches are not substitutes for missing
acceptance. Historical intermittent backend failure was not conclusively diagnosed;
a later green focused run does not establish its root cause.

## Evidence: what actually ran

Counts below belong to different, overlapping stages and must not be added together.
No expensive tests or live acceptance were rerun for this handover.

- Develop integration: 317 selected backend passed, two explicitly gated skips;
  326 frontend passed; TypeScript/build passed, as recorded in its status document.
- CV/publishing gap closure: 231 combined focused backend passed, one disposable
  PostgreSQL gate skipped; a later overlapping 17-case Telegram pass; 331 frontend
  passed and TypeScript/build passed. External providers were mocked.
- Latest face workflow: earlier 82 combined backend passed; latest 23 workflow cases
  passed with both actual-local-model gates enabled; latest **337 frontend passed**;
  TypeScript/build and whitespace checks passed. Existing large interview-bundle
  warning remains. SQL doubles are not live PostgreSQL concurrency acceptance.
- Actual local face models: approved official YuNet 2023mar/SFace 2021dec binaries
  were verified against exact Git LFS sizes/SHA256 and run on original locally drawn
  artificial images. No real person, camera, downloaded photograph or Cloud processing.
- Actual cosine scores: **0.99940291** for a +1 brightness variant of A;
  **0.90649607** for separate procedural design C. The second is also high:
  **identity discrimination was not established**. Transformed-image consistency
  is neither independent identity verification nor liveness/real-world accuracy.
- The encrypted synthetic-reference workflow was tested through real ASGI auth/routes
  and actual model subprocesses, new vault instances and an independent Python
  reader process. The normal backend was not restarted or activated for enrollment.
  References/PNG artifacts from actual tests were cleaned up.
- Historical AssemblyAI evidence used fixed synthetic eSpeak only: finalized roles
  reached F11; graph suggested/valid_suggestion; eight recruiter projections;
  candidate isolation and offline React rendering passed. **Live browser visibility
  remains UNVERIFIED**; natural human cloud speech was not tested. Free-tier training/
  privacy restrictions remain. No new AssemblyAI call is authorized by this handover.

Details: [trainer status](trainer_feature_status_20261026.md),
[CV selection](cv_ai_provider_selection.md), [publishing](multiplatform_job_publishing.md),
[actual matching](face_matching_proof_20261026.md),
[enrollment/viva workflow](face_enrollment_viva_workflow.md),
[F11 finalization](f11_trainer_finalization.md), and
[prior home/office guide](office_home_handover.md). Newer scoped evidence supersedes
older limitations only where explicitly documented; it never grants full BID acceptance.

## What Git will not transfer

Ignored local `data/` includes private runtime profiles, logs/readiness reports,
virtual environments, configured credentials, database/volume contents and approved
STT/face assets. Known categories include the Linux F3/F4 profile, isolated face
OpenCV environment/models/licenses and sanitized run manifests. Model weights are
not committed. Generated face PNGs were deleted. This note transfers no encrypted
vault, encryption key, withdrawal receipt, bearer value or candidate material.

Git also excludes `.env` files, Python environments, node_modules/build output,
CV uploads, recordings/transcripts and databases. Docker images/containers/volumes,
OS native libraries, browser sessions and device permissions do not travel with Git.
Home-only ignored viva notes, if present, need separate individual privacy review;
no ignored file is automatically copied or uploaded here.

Do not copy credentials, browser profiles, private DBs, CVs or biometric artifacts to
Git or an office transfer folder. Use the office's authorized private configuration.
ONNX files are portable assets but transferring/reprovisioning them is a separate
approved action with checksum/license verification. A Linux venv is not portable.

## Windows prerequisites and safe startup

1. Use the authorized GitHub account, Git for Windows, a supported Python version
   compatible with the pinned backend requirements (home tests used Python 3.12),
   and project-compatible Node/pnpm. Home frontend checks used Node 24/pnpm 10;
   inspect the source package files before installing. Do not copy Linux dependencies.
2. Preserve the existing office checkout, private configuration, database and volumes.
   Inspect their branch/status/processes/ports first. Home's port 5288 and older
   baselines on 5188 are different environments; do not confuse them with an office
   service or assume either is active. This handover did not inspect/restart Docker.
3. Create a Windows-local venv and frontend dependencies through the existing guide,
   only after checking resources and approval. Backend now explicitly pins the already
   home-installed `cryptography==50.0.2`. No optional model download is automatic.
4. Determine the expected Alembic head from this source, then read the selected
   office database's identity/current revision before any separately approved
   migration. Historical home baseline was at 0017; do not assume office matches.
   No restore, reset, downgrade or automatic schema upgrade is part of handover.
5. Keep external AI, publishing, SMTP, LiveKit/STT, recording, F11 live processing
   and both face prototypes disabled unless separately configured/authorized.
   Selecting a cloud CV provider requires explicit transfer confirmation.
6. **The encrypted face vault is Linux-only (`fcntl`/POSIX storage controls).** It
   fails closed on Windows; normal startup works with it disabled/unconfigured.
   Do not activate that vault there or copy its Linux key/store blindly. Windows
   protected-storage/locking and key/retention support need a separate reviewed
   implementation before a Windows end-to-end face demonstration. Optional OpenCV
   alone does not remove this blocker. Physical-human biometric use is still blocked.
7. Start only the previously approved office baseline using its verified procedures.
   Confirm local health/authentication and saved jobs before synthetic walkthroughs.
   Do not start optional services or send provider requests merely to check a screen.

## Fresh office worktree (PowerShell, existing authorized clone)

These are instructions for tomorrow, not actions executed on the office laptop.
Run from the office clone and stop if its worktree is dirty, remote is unexpected,
new branch/path already exists, or remote heads differ from the final report:

```powershell
git status --short
git remote get-url origin
git worktree list
git fetch origin
git rev-parse origin/develop origin/feature/trainer-gap-closure-1 origin/feature/face-verification-viva
git worktree add -b codex/office-continuation-20261026 ../TalentTrace-AI-office-20261026 origin/feature/face-verification-viva
```

Use the newly returned directory explicitly. This creates an office-only working
branch from the published face-workflow source without switching/resetting another
checkout. Alternatively, a fresh authorized clone can check out
`feature/face-verification-viva`. Do not merge into develop/main to obtain these
features; they are already inherited on the face branch. Do not force/reset/rebase
if office history differs. Preserve all local environments and private artifacts.

## Recommended next acceptance sequence

1. Verify office source/hash, configuration, DB identity/revision, health and recruiter
   login. Rehearse saved jobs → criteria → stored synthetic applications → scores →
   scheduling → reports/comparison/print without paid/external inference.
2. Review compact analytics acknowledgement and mocked/manual publishing paths.
   Separately approve any real Discord/Telegram delivery with synthetic JD content;
   confirm provider receipts and uncertain outcome handling. LinkedIn remains manual.
3. Plan a fresh separately approved Cloud F3→F4 two-role trial: correct port, fresh
   fictional booking, independent caption/storage/assistant consents, bounded CPU
   and media duration. Do not infer sustained readiness from offline model loading.
4. Then verify visible recruiter-only F11 suggestion, candidate exclusion and active
   withdrawal/disconnection; do not reuse the earlier 15-second visibility claim as
   observed browser acceptance. Preserve one-caption-room safe rejection.
5. Validate screen sharing/attention in approved browser tests, including cleanup.
   They are optional collaboration/coarse status, not cheating detection.
6. Treat Windows face-vault portability and real-biometric governance as separate
   blockers. Keep synthetic face results provisional; do not seek thresholds that
   force design C into a desired label. N1/N19/N21 and remaining BID gates need their
   own small, explicitly authorized completion work.

## Publication safety record

Before writing this note: expected clean branch heads and ancestry matched; remote
`develop` already equalled local `7c2725e`; both requested feature remote branches
were absent; GitHub reported the expected repository private. Six unpublished
commits and 80 blob versions were scanned with no suspicious artifact/credential
findings. The Telegram credential-shaped fixture is explicitly synthetic/nonfunctional.
No ignored data, model, image, DB, secret configuration or biometric reference is
staged. This documentation is reviewed before the ordinary three-branch push;
publication hashes and post-push privacy/cleanliness are confirmed in the final report.
