# Final release integration preparation — 20 October 2026

## Scope and preserved history

Integration branch: `codex/pre-viva-final-integration`, based on published release
`36047ef9cdaff43f574be7a331be8f5f860edabe`. A normal non-fast-forward merge preserves
F4/F11 commits `5809fad`, `fb6221f`, `93cba41` and both parent histories.
Release, main, develop and the separate N19 branch are not changed. Publication
requires separate approval; this document does not assert publication or full BID acceptance.

## Measured evidence and limits

- Wholly synthetic eSpeak benchmark: AssemblyAI English WER **5.88% (3/51 words)**,
  technical terms **12/13**, approximately **2.3 seconds** finalization per role.
  No identical-audio tiny.en comparison exists. This is not natural-speech accuracy.
- The authorized real-provider synthetic browser attempt delivered finalized recruiter
  then candidate captions through F4 and the trusted F11 bridge. The corrected graph
  returned **suggested / valid_suggestion**. There were **eight suggestion-bearing
  recruiter API responses**; candidate responses exposed no suggestion.
- Server publication was 20:12:54.087 Asia/Dhaka, 20 October. Candidate audio end to
  publication was **6.159 seconds**, to the first positive recruiter projection
  **6.762 seconds**. These are server/API timings, not visible-browser latency.
- Offline React checks exercised the real component and response validator: the
  provisional question rendered, disappeared at expiry/withdrawal, and was absent
  for candidates. **Live-browser suggestion visibility remains unverified.**
- Normal completion acknowledged both provider terminations. Active-stream withdrawal
  has offline coverage only; normal finish does not establish its physical acceptance.

Detailed chronology, synthetic fixture hashes and prior test evidence are in
[f4_assemblyai_synthetic.md](f4_assemblyai_synthetic.md). Historical sections describe
individual checkpoints; later measured evidence supersedes their earlier pending gates.

## Privacy and defaults

Faster-Whisper remains the default. `assemblyai_synthetic_enabled` defaults false;
explicit guarded development configuration and both caption/F11 consents are required.
The cloud adapter reads only two server-owned, SHA256-pinned eSpeak WAVs. The cloud
caption route rejects browser binary PCM. No physical microphone cloud STT or real
candidate audio is approved or tested. No provider requests occurred during integration.

External processing transmits synthetic audio to AssemblyAI. Free-tier training opt-out
is unavailable; submitted synthetic audio/text may be used for training. No production
privacy acceptance is claimed. Keep keys in ignored private configuration. Process-local
attempt limits are not distributed quotas. Withdrawal fences later publication but cannot
retract previously transmitted audio. A client deadline cannot guarantee stopped billing.
Self-hosted LiveKit cached-JWT revocation limitations remain.

## N19 decision

Keep `codex/n19-guarded-deletion` separate. Its `0016_submission_deletion` follows
0015 and adds a durable cleanup journal and PostgreSQL external-submission replay
trigger. A nonempty journal intentionally blocks downgrade. It is bounded deletion
of one imported submission in a closed disposable maintenance lab, not candidate-wide
erasure. Interview-bearing records, manual reuploads, new source identities, shared
JSON, external copies and production retention/operator policy remain unresolved.
Merging it would change `alembic upgrade head` from 0015 to 0016 and import behavior;
it needs its own integration/migration rehearsal and explicit scope approval.
N19 diverged at `176ba82b9bb804a719ea0948fbad6e114914e079` and does not contain
the three later release-documentation commits; reconcile documentation during any
future merge rather than replacing the release tree with the N19 tip.
No databases or migrations were changed in this preparation.

## Publication proposal

After reviewing exact branch tips and approving publication, push these explicit refs
without force (no main/develop/release update):

```sh
git push origin refs/heads/codex/f4-assemblyai-synthetic:refs/heads/codex/f4-assemblyai-synthetic
git push origin refs/heads/codex/n19-guarded-deletion:refs/heads/codex/n19-guarded-deletion
git push origin refs/heads/codex/pre-viva-final-integration:refs/heads/codex/pre-viva-final-integration
```

Verify full remote hashes afterwards. Publishing N19 separately does not integrate or
activate it. Recheck remote heads before executing; stop on unexpected differences.

## Integration verification

- Focused backend graph, synthetic adapter, caption, bridge, delivery, copilot,
  LiveKit, invitation and recruiter-record suites: final sequential run **252 passed,
  1 skipped**, 91.22s. The skip is the explicitly configured real local-Whisper
  worker test (`TRANSCRIPT_REAL_WHISPER_MODEL` absent), not a cloud acceptance test.
- Initial overlapping backend/frontend run: **251 passed, 1 failed, 1 skipped**.
  The failure was `test_authorized_bridge_suggestion_private_delivery_and_withdrawal`
  (empty bridge records). It passed alone (**1 passed**) and in the full repeat.
  Resource contention is a hypothesis, not a confirmed root cause; retain this as
  a timing-sensitive test limitation rather than silently discarding the failure.
- Full frontend: **249 passed, 0 failed, 0 skipped**. TypeScript (`tsc -b`) and
  Vite production build passed; existing >500kB LiveInterviewPage warning remains.
- Docker verifier offline unit checks: **2 passed**. Compose configuration validation
  passed using a non-secret placeholder and no service start/build. Baseline Compose,
  Dockerfiles and local recognizer files are unchanged. No Docker runtime acceptance
  was repeated and no PostgreSQL integration/destructive tests were run.
- Diff whitespace check passed. Object audit covered F4/F11, N19 and integration
  changes beyond release: no private-data artifact paths or secret-pattern/known
  private-value matches. Both committed WAVs match the approved synthetic digests.
  This targeted audit is not proof that arbitrary secrets can never exist.
- Private GitHub visibility and published release SHA were verified read-only.
  Proposed new remote branch names were absent. No push occurred.
- Root free space remained approximately **3.3 GiB**; available RAM was approximately
  **0.8–0.9 GiB**, swap almost full. No dependency installs, model downloads, pruning
  or image rebuilds. Further runtime work should first resolve resource pressure.
