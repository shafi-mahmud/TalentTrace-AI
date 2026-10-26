# Submission package — 26 October 2026

Application changes: provider disclosure fix `cc5cfef` and Home/navigation polish
`946458e`, on `feature/office-20261026-acceptance`. Develop/main and remotes are
unchanged. The final documentation commit is identified by Git, not recursively
embedded here. No new F3/F4/F11 trial or harness development was performed.

## Actual demonstration result: PARTIAL, coherent provider-disabled workflow

One continuous browser session used real authentication, API responses and a newly
isolated PostgreSQL database at migration 0017. No frontend API response was mocked.
Only fixture preparation used existing deterministic score builders and a fake
interpreter/generator to persist a sample JD. Those seeded examples are simulations,
not successful AI generation, policy grounding or candidate scoring acceptance.

| Step | Result and actual boundary |
| --- | --- |
| Login → Home | PASS, authenticated browser and saved owned jobs. |
| Create/refine JD | BLOCKED for inference: every provider unavailable. Real UI requests a valid provider; no external model request. Restored sample draft retains Job Reference/revision, but the requested revision was not generated. |
| Saved jobs / Job Reference | PASS; real persisted retrieval and active-job navigation. |
| Publishing preview | PASS; correct saved reference/content; all destinations and review checkbox initially unchecked. No final confirmation/posting. |
| CV intake / extraction | PASS; one additional fictional DOCX uploaded through the browser, locally extracted into two text blocks. No real CV or provider processing. |
| Screening / saved scores | New inference BLOCKED; buttons disabled without a provider. Existing deterministic score fixture retrieved through the real API and used for downstream review. |
| Analytics / notifications | PASS; Job B received/new/viewed 2/2/0 → explicit acknowledgement → 2/0/2 after full refresh. Switching to Job A showed its separate unchanged 1/0/1. |
| Scheduling review / confirm | PASS; native date entry completed by owner because automation could not populate that control. Actual browser review showed 27 October 2026, 11:00–11:45 Asia/Dhaka; final acknowledgement and one Confirm booking click persisted it after refresh. |
| Ownership / persistence | Independent SQL verified recruiter/job/batch/upload/revision, exact UTC time/duration, and unchanged earlier booking. |
| Appointment email | PASS for disabled configuration: Not configured; zero email-attempt rows. No SMTP. |
| Interview access | Saved recruiter interview screen opened. No invitation/token/Join; media, captions, assistant, evaluation and storage controls disabled. Zero new invitation rows. |
| Reports | PASS for actual CV-only F6 retrieval using the selection snapshot. Missing interview evidence and no combined score are explicit. Print control visible; physical printing/PDF not tested. |
| Logout | PASS; sign-in view restored. Later separate sign-ins were used for final visual checks. |

This is not a complete model-backed F1–F6 live run. Frozen evidence remains F3
PARTIAL, current F4 live UNOBSERVED, current F11 live UNOBSERVED.

## Trainer-feature audit

The [fourteen-area matrix](submission_walkthrough_20261026.md#trainer-acceptance-matrix)
maps every recommendation to actual source and evidence. Five areas have bounded
real office verification: Job Reference, CV/job isolation, notifications/analytics,
reviewed scheduling, Home/navigation. The other nine are PARTIAL or BLOCKED;
implemented code is not counted as complete acceptance. Face verification is blocked
for real human identity use; no procedural-image result is relabelled as accuracy.

No submission-critical application logic defect was found in this connected run.
Two unconditional CV messages incorrectly named Groq even though the existing
selector supports local models. They now refer to the selected CV provider; the
separate explicit Groq-transfer checkbox remains unchanged and tested.

## Small UI pass

Home copy is shorter, with existing controls/statuses intact. Shared spacing tokens
make the hero/job cards more compact; navigation uses a consistent two-column grid
on compact screens. No new library, auth/consent change, framework or business-logic
rewrite. Actual screenshots were checked at 480 px and 1528 px, with no horizontal
overflow on those Home/navigation views. This is not exhaustive 390 px/all-device
or accessibility certification. Loading and disabled-provider states were observed;
other error/empty states retain automated coverage.

## Final verification

| Check | Result |
| --- | --- |
| Focused backend: recruiter records, imported batches, appointment email, consolidated report, notifications, provider selection | **66 passed, 19 skipped, 0 failed**. Skips are opt-in PostgreSQL cases; the F6 home fixture requires its explicitly named/ported database. No preserved DB was used to enable them. |
| Fresh real HTTP/PostgreSQL checks | **30 passed**; SQL doubles were not used in this run. The eligible scores were explicitly fixture-seeded outside the HTTP boundary. |
| New browser booking SQL reconciliation | PASS; exact association/time/duration, other booking unchanged, both email-attempt tables empty, invitations absent. |
| Complete frontend suite | **337 passed, 0 failed/skipped**. The earlier 11 focused passes overlap this full suite and are not added again. |
| TypeScript / production build | Both PASS. Existing 567.73 kB lazy interview chunk warning remains; no deadline code-splitting rewrite. |
| Git/links/privacy | Whitespace/local-link checks and bounded sensitive-pattern review passed; no ignored fixtures/credentials/screenshots are staged. |

Execution notes: the first backend test command used the repository-root working
directory and failed collection (`app` import unavailable); rerunning from
`backend/` produced the results above. The copied local launcher initially saw
PostgreSQL's temporary readiness before the requested database accepted SQL. Only
the newly created empty test database was resumed after an exact identity check;
SQL readiness was corrected in the ignored demo copy. A separate Windows hostname
resolution limitation in the HTTP helper was handled by using loopback HTTP, while
the browser retained its isolated hostname. No application defect or preserved DB
change is inferred from either test-tool issue.

## Demonstrate and submit

1. Review the [README setup](../README.md#submission-day-application-and-setup),
   [architecture](architecture/application_overview.md) and
   [walkthrough](submission_walkthrough_20261026.md).
2. Current office demo: `http://submission-20261026.localhost:5276/`, bounded until
   **26 October 2026, 16:14:34 Asia/Dhaka**. Read the local ignored
   `data/submission-demo-20261026/LOGIN.txt` yourself; never paste its contents into
   slides, Git or reports. The source and dependency setup do not include these
   private credentials/data. Do not reuse this fixture after shutdown/expiry.
3. Show Home/job switching/counts, the saved sample draft/reference and publishing
   preview, local CV upload/extraction, saved score evidence, saved reviewed booking,
   disabled email/media and the CV-only report. Explain seeded boundaries aloud.
4. Present the recorded test results and missing acceptance honestly. No Cloud,
   model inference, publishing, email, screen capture or biometric action is needed.
5. Submit only reviewed source, lockfiles, public example configuration and sanitized
   documentation. Never include `.env`, private `data/`, CVs, transcripts, biometric
   artifacts or session/browser profiles. No push/merge was authorized here; publish
   this feature branch or integrate it only after explicit owner review/approval.

## Remaining limits and next work

- Configure/evaluate an approved local model separately for genuine JD refinement
  and CV matching; do not replace disabled-provider states with fabricated output.
- Preserve partial N1 20-CV benchmark, uncertain/unscored outcomes and absent
  all-application numeric ranking policy. Deterministic arithmetic is not LLM quality.
- Freeze additional Cloud troubleshooting for submission. Current live F4/F11,
  simultaneous candidate exclusion, withdrawal and transcript acceptance remain open.
- Full-duration F4, simultaneous caption rooms, network recovery and cached media
  token revocation remain limited. F5/F6 combined live report/print acceptance is open.
- Real platform/email delivery, multi-worker publishing deduplication, trustworthy
  physical face verification, candidate-wide N19 deletion and complete clean-machine
  N21 Docker/model deployment are not claimed.

Ignored evidence: `data/submission-demo-20261026/` contains browser step records,
sanitized screenshots, actual API assertions and booking SQL verification. No private
identifiers, login values or candidate material from that directory are copied here.
