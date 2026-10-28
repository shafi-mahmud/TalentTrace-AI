# Deadline core closure — 28 October 2026

**Overall: PARTIAL.** Published develop baseline: `30468aca4a0ee43d8a315dd5bdd43269711507b9`. Work remains on `feature/office-20261026-acceptance`; no merge, push, tag or production deployment in this task. The running Groq application, its database/configuration and other worktrees are preserved.

**Owner-reported trainer clarification:** the project owner reports that the trainer subsequently permitted AI assistance. No independent approval document was supplied or verified. This records the report, not invented approval evidence or a claim about originality.

## Fixed and verified

| Increment | Confirmed defect / correction | Verification boundary |
| --- | --- | --- |
| F4 generated WAV selection (`2ab3280`) | Join could race an unfinished decode; old decodes could overwrite newer selections; a failed replacement left the previous buffer; toggling generated media removed the native input subtree. Added a generation fence, synchronous pending guard, context/unmount invalidation, explicit ready/loading status, stale-buffer clearing and a stable hidden input subtree. | New regressions failed before the correction. Selected-buffer publication, pending Join denial, replacement ordering, disposal and toggle retention pass through the existing component/VM test pattern. No auth, caption/storage consent, STT decoder or provider path was weakened. |
| N19 inventory (`2faea9c`) | The current schema's `booked_interview_email_attempts` FK was omitted, causing an unmapped dependency rather than an exact count. Added the interview-scoped relation. | Actual disposable PostgreSQL inventory includes the target attempt, excludes another application's attempt, remains read-only and reports no unmapped table for this known FK. Existing related-record deletion refusal remains enforced. **This is not general deletion.** |
| F1/F2 acceptance fixture (`44cba43`) | Old fixture patched a superseded service constructor and omitted current provider/transfer headers; HTTP 422 was correct. Updated only the test to exercise real provider/consent selection with deterministic extraction/matching. | Complete fixture stores/reloads 20 outcomes, preserves uncertainty, arithmetic/ties/evidence and rejects wrong ownership/revision. A terminal fake rescreen preserves the earlier complete saved results. No production scoring, ranking, retry or persistence policy changed. |
| Reviewer configuration (`19a3651`) | A single hardcoded output profile prevented another independent setup without manually constructing a secret-bearing env file. Added `--output` restricted to new `.env` paths under ignored `data/`. | Default remains compatible; independent secrets, rejected unsafe paths/ports and no-overwrite behavior pass. Used for the new disposable Docker proof. No existing configuration is imported or overwritten. |

README now explains F1–F6/F11, architecture/technology choices, LangGraph boundaries, privacy/fairness, baseline versus provider prerequisites and complete fresh setup commands. Earlier README milestones remain collapsed historical evidence. The startup guide links the current procedure instead of silently treating 0015-era proof as current.

### F4 historical failure: what remains unknown

The exact October 28 “No file chosen” occurrence was not independently reproduced in its original browser. Source inspection found no automatic reload in the interview component. The retained demo Vite configuration disables HMR. Route/context remounts and genuine reloads still clear native file selection by design; audio is not copied to localStorage or the server to bypass this boundary. The confirmed toggle/decode defects above do not prove the original reset or zero-caption root cause.

The two approved synthetic WAVs match their committed SHA-256 values, mono PCM16/16 kHz format, nonzero signal and documented 7.2568125/14.751875-second duration. Their known-reference speech is documented in the [fixture README](../backend/app/integrations/stt/synthetic/README.md). A WebAudio/SDK-double test verifies that the chosen buffer feeds the published synthetic microphone destination rather than the tone generator. This is **not new browser audio delivery, intelligibility or external recognition acceptance**. Full live F4 remains PARTIAL.

For a separately authorized future test: reach the final interview page first; expand Generated speech, select the role WAV and wait for “Ready in memory”; do not reload or change interview context. Join remains unavailable while decoding. If the ready status is absent, select again rather than treating a tone-only publication as speech. Existing caption/storage consent sequence and bounded provider limits remain mandatory. No new trial, booking, invitation or token was created here.

## N21: fresh same-host Docker proof

**Current-host disposable startup: PASS. Overall N21: PARTIAL.** Unique project `tt-final-467ef387c3`, loopback port 5298, two new project-scoped named volumes; no preserved env, database, volume, port or image tag reused as runtime state. Standard current backend/frontend Dockerfiles built. An initial deliberately network-disabled build failed resolving public Debian packages before services started; the documented standard build succeeded. This was not an application defect or a reason to weaken runtime networking.

- Verified expected new database/user and **zero public tables before migration**; explicitly migrated only that database to the single `0017_booked_interview_email` head.
- Backend/frontend healthy; existing `docker/verify.py` passed **9 grouped checks**: private backend/database networking, current schema, frontend/API/SPA/private-path routing, safe unavailable providers, real fictional-recruiter authentication and origin checks, candidate/foreign-owner denial, saved Job Reference/revision/session/file-marker persistence after all three containers were recreated, logout and sanitized log checks.
- No Groq/LiveKit/AssemblyAI/SMTP/publishing/model request. Public build dependency traffic is separate from provider inference. No model weights downloaded by the application setup.
- All three proof containers stopped with **exit codes 0/0/0**; both named volumes/evidence retained. Every pre-existing container's ID, image, start time, state and mounts matched its preflight snapshot. Groq remained healthy and unchanged.
- Free RAM observations: 3461 MiB initially, 3387 MiB before backend startup, 3076 MiB after verification. These are sampled readings, not continuous telemetry.

This used the current Windows host/Docker engine and its dependency cache. It is not a second clean-machine installation or complete configured-provider deployment. No public HTTPS/mobile deployment or comprehensive security certification is implied.

Executed from the worktree root (private env already created for this owned proof):

```text
docker compose -p tt-final-467ef387c3 --env-file data/deadline-closure-9153cdc9b1/runtime.env -f compose.yaml build --pull=false backend frontend
docker compose -p tt-final-467ef387c3 --env-file data/deadline-closure-9153cdc9b1/runtime.env -f compose.yaml up -d --no-build --pull never --wait db
# Only after checking new-volume ownership, database identity and empty schema:
docker compose -p tt-final-467ef387c3 --env-file data/deadline-closure-9153cdc9b1/runtime.env -f compose.yaml run --rm --no-deps --pull never backend python -m alembic upgrade head
docker compose -p tt-final-467ef387c3 --env-file data/deadline-closure-9153cdc9b1/runtime.env -f compose.yaml up -d --no-build --pull never --wait --wait-timeout 180
python docker/verify.py --project tt-final-467ef387c3 --env-file data/deadline-closure-9153cdc9b1/runtime.env --allow-synthetic-records
docker compose -p tt-final-467ef387c3 --env-file data/deadline-closure-9153cdc9b1/runtime.env -f compose.yaml stop --timeout 25
```

Do not rerun the synthetic-record verifier on preserved data. For a reviewer, use the fresh-project [README quick start](../README.md#reviewer-quick-start--fresh-provider-disabled-docker-deployment); ordinary subsequent startup is one documented `up -d --wait` command after explicit first-time configuration/migration/provisioning. Private locator: `data/deadline-current.json`; logs, checksums, ownership snapshots and stopped-resource receipts are ignored, not submitted credentials.

## N19 linked-data scope and exact blocker

The deletion unit must be an explicitly owned job/batch/upload, never a candidate name or guessed cross-job identity. Inspection established these dependencies; **no ordinary candidate deletion was performed**:

| Associated data | Actual relation / required handling |
| --- | --- |
| CV and intake provenance | Exact owner/job-reference/batch/upload file and `external_cv_submissions`; preserve source deduplication/deletion fence. Native storage and shared batch metadata also need an explicit erasure contract. |
| Scores and confirmations | All matching `candidate_scores` revisions, `reviewer_confirmations` and `application_views`; other uploads/jobs must remain untouched. |
| Booking / joining access | `interview_schedules` screening snapshot and `interview_invitations`; terminate/revoke active access before deleting dependent state. Cached media grants/remote participants cannot be erased by deleting a local row alone. |
| Scheduling and email | `scheduling_invitations`, their `interview_email_attempts`, and now inventoried `booked_interview_email_attempts`. Uncertain sends must not become resend permission after deletion. |
| Transcript / F5 | `interview_transcript_sessions`, turns, `transcript_privacy_access`, `interview_analyses`; coordinate withdrawal, retention, active writers and existing deletion receipts. Never reconstruct withdrawn content. |
| Shared and transient data | Job-scoped bulk scheduling preview/outcome JSON can reference several applications; F11/caption/evaluation state and optional face vaults have separate lifecycles. Do not delete an entire shared operation to erase one application. |
| External copies | Original Google/Drive data, email recipients, provider retention, backups/WAL and exported reports are outside a local file unlink; disclose rather than claim erased. |

The existing delete command is constrained to a closed Linux maintenance lab, with writer admission shut, exact inventory/plan digest, durable tombstone and post-commit file verification. It rejects related interview/scheduling/shared/unknown records. Generalizing it now would require coordinated privacy/worker/access shutdown, transactional dependency handling, shared-JSON redaction and recoverable filesystem erasure. **That extension was stopped as too broad/risky for this task.** The new inventory is accurate; N19 remains PARTIAL. Transcript withdrawal is not full candidate erasure.

## F5/F11 and N1 reconciliation

Current F5 eligibility still requires recruiter ownership, current job/revision, established retention, consented/non-withdrawn evidence and finalized accepted capture/turn validation. The proposed retained alternative source previously had an owner mismatch; no credential reset, allowlist bypass, source reconstruction or evaluation occurred here. F11 still consumes trusted `_publish_caption` events through LiveBridge and its real model-free graph, with separate assistant consent, recruiter-only projection and no own transcript/suggestion storage. Focused tests passed; **no new real F4→F5/F11 end-to-end PASS**.

The N1 historical provider run remains 20 parsed / 19 decisions / 4 numeric / 11 eligible-unscored / 4 excluded / 1 terminal 429, 449.09 s. Ambiguous positively weighted evidence deliberately abstains. The corrected offline complete fixture has five numeric scores because its explicitly defined final fake outcome succeeds; it is not a claimed improvement to that historical run. Failed fake rescreening preserves the prior complete saved projection. Existing retry tests confirm two short-reset explicit-429 retries at most within a 60-second wait budget; daily limits, missing/unsafe reset metadata, validation errors and uncertain timeouts are not retried. Today's provider quotas were **not queried or assumed**; no real 20-CV batch ran.

## Final verification and submission material

- **155 frontend tests passed, 0 failed/skipped**; **115 backend/helper tests passed, 7 skipped** in the final runs. TypeScript and production build PASS; existing >500 kB interview bundle advisory remains.
- Skips: one Windows symlink-privilege case and six separately opt-in PostgreSQL F5-input tests. The current inventory's own disposable PostgreSQL test **did run**; previous accepted F5/F6 connected/browser evidence remains separate.
- Regressions failed before fixes. Intermediate runs exposed a missing timer stub in the new VM test and the stale F1 fixture; these were corrected without relaxing production contracts. Final counts do not add failed/repeated attempts together.
- Four final uploaded WBS/SRS/HLD/System Design files remain unchanged and linked from [Start here](00_START_HERE.md#final-submission-documents). No new PowerPoint or separate downloaded README guide was found in the worktree/document tree; no presentation review is claimed. WBS filename says v1.0.0 but internal approval/completion is not inferred.
- No real candidate data, physical audio/video, biometric execution, paid services, messages/emails, provider trials, protected-database migrations or Groq deployment changes. Original dirty checkout and existing worktrees preserved.

## Remaining blockers, ranked

1. **N19 functional gap:** general owned-application/candidate-associated erasure, including linked lifecycle/shared/external data, is not complete.
2. **N1 acceptance gap:** full real 20-CV quality/performance/scoring coverage is not established; never manufacture numeric scores to close it.
3. **F4→F5/F11 live chain:** real recognized/stored browser speech feeding grounded evaluation/co-pilot remains partial; historical reset/zero-caption cause is not proven by offline fixes.
4. **N21 / remote deployment:** second clean-machine/full-feature setup and approved HTTPS/remote-device operation remain unverified.
5. **Submission review:** final PowerPoint/content approval and review of the new local commits before publication remain owner actions.

**One safe release action:** review these closure commits and their disclosed gaps, then separately authorize integration/publication to develop. No new external trial or main merge is required to preserve and submit existing evidence.
