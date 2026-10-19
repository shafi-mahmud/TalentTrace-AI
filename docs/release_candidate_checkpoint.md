# Pre-viva release-candidate documentation checkpoint

19 October 2026; viva 22 October 2026. **Reviewable proposal, not a release or full
BID acceptance.** No application code, migrations, database state or runtime
configuration is changed by this checkpoint. Publication of the release branch
through `5b6f172` was explicitly approved and completed. This handover update is a
local documentation commit pending separate push approval; no merge is approved.

## Current handover status

Published private origin: `feature/pre-viva-release-docs` at
`5b6f1729e0ec90fe65af0057e24ac6f2b8554d16`, verified 19 October.
The nine Docker/F11/release/benchmark commits previously unpublished are now
reachable there. N19 remains separate at `4d37ba5`, with four unpublished commits.
See the [Linux home handover](office_home_handover.md).

## Code base and history

Proposed code base: `feature/f11-copilot-live-integration`,
`176ba82b9bb804a719ea0948fbad6e114914e079`.
Documentation worktree: `TalentTrace-AI-release-docs`, branch
`feature/pre-viva-release-docs`, initially at that exact commit. N19 remains at
`4d37ba56980d0cf126c01d63c8cea7e5a325fc6d` in its existing worktree.

Verified ancestry includes published Milestone 3 `2967ae9`, F6 `e059709`, Docker
`e33d26b`, and the ordered F11 logic/hardening/delivery/live integration commits.
Historical pre-publication snapshot: the proposed base had seven unpublished
ancestor commits; N19 had those seven plus four more (eleven). Publication of
`5b6f172` supersedes that count: only the four N19 commits remain unpublished
within these two lines of work. The historical table below preserves their scope.

| Full commit | Subject | Release disposition |
| --- | --- | --- |
| `7ac71c5d8a2d860145ce90cf6b8423e141dce698` | build(docker): add isolated three-service synthetic startup | Release ancestry; now published through 5b6f172 |
| `e33d26b63bdc42f946c97c3a7ca5303e6679c72b` | test(docker): verify isolated authentication and persistent startup | Release ancestry; now published through 5b6f172 |
| `70956e14a37f2c4d87569a0728c1eb37473cd8ec` | feat(copilot): add bounded contextual question logic | Release ancestry; now published through 5b6f172 |
| `687797e3206c786f125a174b45414d9de91d7194` | fix(copilot): reject unrelated and uncertain live responses | Release ancestry; now published through 5b6f172 |
| `8c3957ea877d3a091cb8e615c1b4e8be1ec84e00` | feat(copilot): add consent-scoped interviewer delivery | Release ancestry; now published through 5b6f172 |
| `39188217d29928e2a9494592cfd512a84d38421a` | feat(copilot): integrate trusted caption events with consent fences | Release ancestry; now published through 5b6f172 |
| `176ba82b9bb804a719ea0948fbad6e114914e079` | docs(copilot): record integration tests and blocked live readiness | Release ancestry; now published through 5b6f172 |
| `3babfca6a37cfdfabac052a666daccd6f11e69fd` | feat(privacy): add candidate data deletion inventory | Separate N19 history; preserve, not proposed release code |
| `584dd04cfe47726c7822086d2b4d960feda08240` | feat(privacy): add deletion maintenance preflight | Separate N19 history; preserve, not proposed release code |
| `6b8b7b8f88448ec3ce327eaca3fb3d9815f9d12a` | feat(privacy): add isolated deletion maintenance controls | Separate N19 history; preserve, not proposed release code |
| `4d37ba56980d0cf126c01d63c8cea7e5a325fc6d` | docs(privacy): record partial N19 maintenance acceptance | Separate N19 history; preserve, not proposed release code |

The seven Docker/F11 commits are now in the trainer-visible private repository.
Preserve their incremental ancestry rather than copying
files into an older branch. The four N19 commits document partial work and should
remain recoverable/reviewable separately; they must not be presented as completed
candidate deletion. This documentation checkpoint records known limitations and
AI assistance; it does not certify originality or independent-design compliance.

Published recovery anchors from the audit: main `171937e`, develop `2cd7536`,
Milestone 3 `2967ae9`, F6 `e059709`, notifications `4b25a27`, LinkedIn `ccb19e5`.
Main/develop are older than the proposed release. Notifications, LinkedIn and the
external-intake branch are not integrated by commit ancestry. Some required intake
bridge functionality was separately implemented in F4; that does not integrate the
whole external-intake branch. No merge, cherry-pick or rebase was performed;
only the explicitly authorized release-feature push occurred.

## Acceptance and privacy gates

See the [requirement matrix](release_traceability.md) and
[innovation rationale and assistance disclosure](f11_innovation_rationale_draft.md).

- N1: the earlier 12-CV result (196.63 seconds) remains historical. One real
  20-input run at `b3c00db` took 449.09 seconds: 20 parsed, 19 decisions, four
  numeric scores; N1 remains PARTIAL. The README records the measured result.
  No second batch or inference was run for this handover.
- N19: PARTIAL on a separate branch. Inventory/preflight/maintenance controls are
  implemented there; deletion, tombstones, suppression and recovery are absent.
  The lab remains maintenance-blocked; do not restore access or run cleanup from
  this documentation checkout. No person-wide candidate identity is inferred.
- N21: isolated current-source validation at `b3c00db` passed image builds,
  migration 0015, authentication/routing and recreation persistence; subsequent
  commits changed documentation only. Eight Docker helper and 31 backend tests
  passed in that task. This is still not complete clean-machine acceptance:
  baseline Compose has no enabled local media/STT or full F5 runtime.
- F11 physical end-to-end acceptance is pending; mocked recognizer tests are not
  microphone acceptance. The graph is bounded deterministic pattern processing,
  not general semantic understanding or a competence assessment.
- Self-hosted LiveKit 1.13.10: local invitation/session revocation denies future
  application access but does not guarantee invalidation of already-issued or
  refreshed media JWTs. RemoveParticipant/absence/elapsed time do not prove token
  revocation; DeleteRoom does not prove prevention of recreation. Fresh independent
  demonstration rooms are not a production revocation fix. Durable room-generation
  isolation remains planned, not implemented here.
- Transcripts remain imperfect accepted-audio captures. Do not describe a short
  synthetic result as a complete interview or comprehensive candidate competence.
- No secrets/private records belong in Git. Existing ignored evidence must remain
  private; ignore rules do not replace tracked-file/history review before publishing.

Current migration graph is linear through `0015_reviewer_confirmation`.
Notification `0011_application_views` is already byte-identical, but its feature
is separate. External-intake independent 0006–0008 revisions require explicit
migration design; a broad merge is unsafe without review. Do not apply migrations
against existing demos for release validation.

## Exact next validation tasks — recommended, not executed

1. Owner reviews scope, requirement gaps and rationale; confirms independent
   authorship/originality and intended trainer-visible history. Estimate 2–3 hours.
2. Reproduce the baseline on Linux using the handover guide. Office validation
   already passed; do not repeat the provider benchmark by default. Investigate
   the existing N1 uncertain-experience evidence offline before proposing any
   separately approved new provider run. Estimate 3–5 hours; retain Docker gaps.
3. One bounded authorized physical F11 acceptance: microphone→local STT→trusted
   events→private suggestion, then candidate isolation and withdrawal. No automatic
   retries or inferred success. Estimate 2–3 hours. If blocked, freeze PARTIAL.

N19 is still mandatory unfinished work, not deferred compliance. Safe completion
needs a separately reviewed cleanup increment with interrupted-recovery and
re-import-suppression acceptance. Do not rush deletion into the viva build.
Optional LinkedIn/notifications integration, broader ASR/retrieval changes and
unrelated features should wait until these gates are resolved.

## Evidence policy

Counts in linked documents are historical, overlapping scoped suites, not a new
full-suite run. Missing README links were removed instead of fabricating official
WBS/clarification documents. Historical implementation notes are retained; this
checkpoint and the matrix describe current scope and supersede stale status
summaries. No trainer clarification was independently located in this audit.
