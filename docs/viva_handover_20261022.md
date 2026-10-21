# TalentTrace AI — office viva handover, 22 October 2026

Viva: **22 October 2026**, Asia/Dhaka. This is a source-and-evidence handover,
not trainer acceptance or a promise that every integration is active. The client
calendar is already 22 October: confirm the actual office/viva schedule rather
than interpreting “tomorrow” as the viva date.

## A. Source state and branches

Private repository: `shafi-mahmud/TalentTrace-AI`. Read-only GitHub checks during
this handover confirmed these full remote tips:

| Remote branch | Commit |
| --- | --- |
| `develop` | `480184c2321c6520bbb00754d1aa5a054003c03e` |
| `codex/pre-viva-final-integration` | `480184c2321c6520bbb00754d1aa5a054003c03e` |
| `codex/f4-assemblyai-synthetic` | `93cba41c5d1a8b0bac2069b5061f8637cb4f6dac` |
| `codex/n19-guarded-deletion` | `44c1b0b41f7ed9cdc0d25d47691f2cc6de15fb90` |

The three implementation worktrees and the baseline were clean when inspected.
The local N19 branch still tracks the older `origin/feature/n19-candidate-deletion`
(ahead by two commits); that tracking label does not contradict the published
`codex/n19-guarded-deletion` tip above. Remote truth was checked with `ls-remote`.

Integration lives at `/home/shafi/Projects/TalentTrace-AI-final-integration-20261020`.
It preserves F4/F11 commits `5809fad`, `fb6221f`, `93cba41` through normal merge
`a8ed340`, followed by documentation `480184c`. N19 is not merged into this source.
The separate Docker baseline is
`/home/shafi/Projects/TalentTrace-AI-pre-viva-20261020`, branch
`feature/pre-viva-release-docs`, HEAD
`36047ef9cdaff43f574be7a331be8f5f860edabe`.
This handover is the sole change on `codex/viva-handover-20261022`, created from
verified `origin/develop`. Its eventual commit hash is reported outside this file
so it does not require a self-referencing commit.

## B. Architecture and code evidence map

Paths below are relative to the repository. Entry points are
[`frontend/src/main.tsx`](../frontend/src/main.tsx),
[`frontend/src/App.tsx`](../frontend/src/App.tsx),
[`backend/app/main.py`](../backend/app/main.py) and
[`backend/app/api/router.py`](../backend/app/api/router.py).
React/Vite/TypeScript calls FastAPI under `/api/v1`; routers validate/authenticate,
services implement business rules, SQLAlchemy models persist authorized state in
PostgreSQL. Alembic head in this integrated source is `0015_reviewer_confirmation`.

| Area | Actual source and role |
| --- | --- |
| JD prerequisite | `api/routers/job_descriptions.py`, `recruiter_chat.py`; `agents/jd/workflow.py`: retrieve policy → generate draft → validate. Company-policy BGE/pgvector retrieval grounds citations; configured Groq generates structured drafts. Manual job creation is a separate supported route. |
| F1 screening | `api/routers/cv_uploads.py`, `screening.py`; `services/cv_upload.py`, `cv_extraction.py`, `cv_ocr.py`, `candidate_profile.py`, `screening_matching.py`, `screening_ranking.py`; `agents/screening/workflow.py` validates sources, matches evidence, validates provider interpretations and applies hard requirements. `CvIntake.tsx` and screening presentation render outcomes. |
| F2 scoring | `services/candidate_scoring.py`, `score_records.py`; `schemas/candidate_score.py`; `SavedScores.ts`, `ScoringWeightsEditor.ts`, `ScreeningCriteriaReview.ts`. Deterministic weighted coverage uses validated F1 evidence, separate eligibility and explicit not-scored states. |
| F3 scheduling/media | Routers `interviews.py`, `self_scheduling.py`, `interview_access.py`, `bulk_scheduling.py`; services `interview_booking.py`, `interview_slots.py`, `livekit_interview.py`; `InterviewSchedulingPage.ts`, `CandidateScheduling.ts`, `LiveInterviewPage.tsx`. Owned persisted selection snapshots support booking; authorized LiveKit tokens support browser media. |
| F4 captions/storage | Router `interview_captions.py`; `services/interview_captions.py`, `caption_transcript.py`, `interview_transcripts.py`, `transcript_consent.py`; `integrations/stt/local_whisper.py`; `InterviewCaptions.tsx`, `TranscriptPanel.tsx`. Independent consent and source/time attribution are retained. Optional synthetic cloud adapter is separate from local decoding. |
| F5 interview evaluation | Router `interview_analysis.py`; `agents/evaluation/workflow.py`; `services/evaluation_input.py`, `interview_qa.py`, `interview_mapping.py`, `durable_interview_analysis.py`; `InterviewAnalysis.tsx`. Authorized transcript evidence feeds source-linked evaluation; durable reads validate source eligibility. |
| F6 consolidated assessment | Router `consolidated_assessment.py`; services `assessment_discovery.py`, `consolidated_assessment.py`, `reviewer_confirmation.py`; schemas `consolidated_assessment.py`, `reviewer_confirmation.py`; `ConsolidatedAssessment.ts`, `CandidateComparison.ts`, `SuitabilityEvidence.ts`, `ReviewerConfirmation.ts`. Reuses persisted F2/F5 rather than running inference on report reads. Native print/export, comparison and explicit qualitative reviewer confirmation are separate concerns. |
| F11 interviewer co-pilot | Router `interview_copilot.py`; `services/copilot_live.py` trusted caption bridge, `copilot_delivery.py` scoped runs/consents/projections; `agents/copilot/workflow.py` deterministic LangGraph; `InterviewCopilot.tsx`, `api/copilot.ts`. No new LLM call is needed for its follow-up graph. |

Backend paths in the table are under `backend/app/`; frontend component paths
are under `frontend/src/components/` unless stated otherwise. The chatbot
orchestrates the JD graph; it is not another independent assessment graph.

Persistence entry points: `backend/app/db/models/recruiter.py` contains Recruiter,
RecruiterSession, JobProfile, CandidateScoreRecord, InterviewSchedule and invitations;
`interview_transcript.py`, `interview_analysis.py`, `reviewer_confirmation.py` hold
transcript, persisted F5 and human confirmation records. `knowledge.py` holds
policy/reference chunks and vectors. There is no universal person-wide candidate
registry: exact application identity is `(job_id, batch_id, upload_id)`; intake
files and ledger records must not be mistaken for one global candidate table.

## C. Recruitment workflow and current manual observations

Intended implemented flow: sign in → create/save job (manual or configured JD
assistant) → review criteria/weights → upload CVs → extract text/profile → screen
and score eligible evidence → select exact application → schedule/invite → join
LiveKit → independently consent to captions and optional assistant processing →
review authorized F5 analysis → F6 report/comparison/print and optional human
confirmation. Missing dependencies block their own stages; opening a page does
not establish end-to-end completion. Publication/email requires separate action.

Latest home walkthrough observations below are **user-reported**, supplemented by
the previously verified startup; they were not replayed during this documentation task:

- Three Docker baseline containers started healthy; frontend and API health returned 200.
- Recruiter login succeeded with a newly provisioned synthetic account.
- JD Assistant page worked, but recruiter chat was not configured in that Docker environment.
- Manual job creation succeeded. Python was confirmed must-have; FastAPI preferred.
- Provisional weights were 50/30/20 (skill/experience/education), not BID-mandated values.
- One synthetic PDF uploaded; local PDF text extraction succeeded.
- Candidate profile extraction was unavailable because Groq was not configured.
- **Interview Scheduling is the next manual walkthrough stage.** Without an eligible
  saved application, inspect its UI/history only; do not fabricate scores or screening
  evidence to bypass selection gates. Use an authorized existing fixture if available.

## D. Evidence and remaining acceptance gaps

**F11:** authorized real AssemblyAI calls used only fixed, server-owned eSpeak audio.
Both speaker captions reached the trusted F11 bridge, and LangGraph returned
`suggested / valid_suggestion`. Eight recruiter API projections contained a suggestion;
candidate isolation passed. Real React component/validator rendering passed offline.
**Live-browser suggestion visibility remains UNVERIFIED. Natural human-speech cloud
transcription was NOT tested.** Both provider sessions acknowledged termination.
Normal finish is not proof of active-stream withdrawal acceptance.

Synthetic benchmark WER was **5.88% (3/51 words)**; technical terms **12/13**;
finalization approximately **2.3 s per role**. The later integration measured
**6.159 s** from candidate audio end to server suggestion publication and **6.762 s**
to first positive recruiter API projection; neither is visible-browser latency.
No identical-audio tiny.en comparison or accented natural-speech acceptance exists.

AssemblyAI is disabled by default. Its adapter accepts only two hash-pinned synthetic
WAVs and cloud mode rejects browser microphone PCM. Both caption and F11 consents
are required. Free-tier training opt-out is unavailable: synthetic audio/text may
be used for training. Consent withdrawal cannot retract transmitted data; client
timeouts cannot guarantee zero further billing. Process-local attempt guards are
not distributed quotas. No real hiring-data cloud approval is implied.

Other important limits:

- **N1 PARTIAL:** recorded 20-input run took 449.09 s: 20 parsed, 19 decisions,
  only four numeric scores, 11 eligible-unscored, four excluded, one terminal 429.
  Full 20-CV scoring/ranking acceptance is absent.
- **N19 PARTIAL, separately branched:** guarded deletion of one imported submission
  has synthetic lab evidence, journal/retry and known-source re-import fencing.
  Person-wide deletion, interview-bearing dependencies and general reupload
  suppression remain unresolved. Its migration 0016 is not in develop; do not apply
  it to an existing demo merely because that feature branch exists.
- **N21 PARTIAL:** three-service Docker baseline is not full-feature deployment
  acceptance; LiveKit, STT, evaluation, email and other integrations are not all enabled.
- Self-hosted LiveKit cached-JWT revocation remains limited; do not claim immediate
  revocation of every already-issued media token.
- F11 human-audio end-to-end acceptance is incomplete. Local tiny.en physical
  technical-vocabulary accuracy was poor; synthetic cloud evidence does not replace it.
- F6 still needs full print/PDF/pagination/cancellation and combined-evidence browser
  acceptance. Historical F2 requirement evidence cannot always be reconstructed;
  multiple eligible F5 versions require a clear ambiguity policy, not arbitrary selection.
- Retention, deletion and external-copy governance need production review. Source
  availability is not candidate quality; restricted/missing evidence is not a zero score.
- An initial intermittent bridge test failure was not conclusively diagnosed.
  Do not present resource contention as its proven cause.

## E. Environment and safe Windows continuation

The Linux baseline uses Docker Desktop `desktop-linux`, project `talenttrace-home-viva`,
loopback frontend `http://127.0.0.1:5188/`, and database `talenttrace_docker_demo` at
0015. Named volumes are `talenttrace-home-viva_postgres_data` and
`talenttrace-home-viva_application_data`. Private config is `data/docker-demo.env`;
local health timing override is `data/stage-a-20261020/healthcheck.override.yaml`.
These files and volumes are **not included in Git** and must not be copied blindly.
The baseline Compose disables copilot/live, LiveKit demo, transcript storage,
interview evaluation/email and reviewer confirmation; previous native home F6
activation is a different runtime. Integration source does not update an old image.
No Docker service was started/stopped or runtime state reverified for this handover.

Office procedure:

1. Preserve the Windows checkout, private configuration and existing database first.
   Use normal GitHub authentication; never place credentials in Git URLs.
2. Fetch and inspect `origin/develop`; verify full HEAD `480184c…`. Use a separate
   worktree/branch for study changes. Fetch the documentation branch only after its
   push is approved and verified. Do not reset or overwrite an existing checkout.
3. Check Docker context, available ports/RAM/disk and project-labelled volumes.
   Linux paths, virtual environments, cached models and executables are not portable
   Windows installations. Use existing Windows tooling and documented PowerShell
   equivalents; do not paste Linux absolute paths as Windows commands.
4. Consult [Docker startup](docker_startup.md) and
   [home setup guide](office_home_handover.md). Inspect private-config presence locally;
   the helper refuses overwrites. A new Compose project creates an empty environment,
   not a copy of home data. Do not run init/migration/reset against an unverified target.
5. Read-only verify the intended database identity and Alembic revision before writes.
   Missing models/provider settings should be reported, not silently installed or enabled.
   Do not copy home dumps, browser sessions, invitations or provider keys into the repo.
6. If the exact existing home baseline is being resumed, its known command is below;
   it is reference for Linux, not a claim that these ignored files exist in Windows:

```sh
docker compose -p talenttrace-home-viva --env-file data/docker-demo.env \
  -f compose.yaml -f data/stage-a-20261020/healthcheck.override.yaml \
  start --wait --wait-timeout 180 db backend frontend
```

No rebuild, `down -v`, pruning, migrations, new accounts or external inference are
needed to read this handover. Limited Linux disk (~3.5 GiB free at inspection) and
7.6 GiB RAM remain constraints; do not transfer Docker Desktop storage onto NTFS.

## F. Verified tests — historical results, not rerun today

| Evidence checkpoint | Recorded result / limitation |
| --- | --- |
| Integration backend | 252 passed, 1 skipped (91.22 s); optional real-Whisper model gate absent |
| Initial overlapping backend run | 251 passed, 1 failed, 1 skipped; empty bridge records. Failed test then passed alone and in full repeat; cause unresolved |
| Integration frontend | 249 passed; zero failed/skipped |
| TypeScript and Vite build | Passed; existing >500 kB LiveInterviewPage chunk warning |
| Docker verifier offline tests / Compose validation | 2 passed / configuration passed; not another runtime or PostgreSQL acceptance run |
| Earlier F6 synthetic-home activation | 111 backend including PostgreSQL cases; 231 frontend, no failures/skips in that scope; distinct native runtime |

Counts overlap and must not be added. Backend tests are in `backend/tests/`, frontend
in `frontend/tests/`. Useful entry points: `test_copilot_prefaced_questions.py`,
`test_assemblyai_synthetic.py`, `test_copilot_live.py`, `test_copilot_delivery.py`,
`test_interview_copilot.py`, `test_self_scheduling_postgres.py`,
`test_consolidated_assessment.py`, `test_reviewer_confirmation.py`; frontend
`copilot.test.ts`, `captionLifecycle.test.ts`, `schedulingPage.test.ts`,
`assessmentPrinting.test.ts`, `candidateComparison.test.ts`.
No provider request, application regression run or database modification was made
for this documentation-only task.

## G. Viva explanations and next study sequence

- **Why separate F1/F2/F6?** F1 matches evidence and gates eligibility; F2 computes
  weighted coverage; F6 presents authorized combined evidence and a human-reviewed
  qualitative position. None is an automatic hire/reject decision.
- **Why deterministic F11?** A bounded question/answer graph can abstain, validate
  requirement/source references and avoid an extra paid inference call. The prefaced
  question helper is shared across assembly and validation; arbitrary “how/explain”
  occurrences, quoted instructions and negation are not blanket question evidence.
- **Why exact identities and revisions?** They prevent mixing uploads/jobs or treating
  rescored/revised evidence as the original reviewed source. F6 rechecks freshness,
  consent, retention and fingerprints. Read transactions use REPEATABLE READ for
  consistent report projections; a snapshot cannot retract a response already sent.
- **How does F3 prevent double booking?** `interview_booking.lock_interviewer()`
  selects the active recruiter row with SQLAlchemy `with_for_update()`. Cooperating
  booking paths serialize on that row before overlap checks; PostgreSQL holds the
  row lock to transaction end. This does not lock the entire database or solve
  writes that bypass the protocol. Unique application constraints also guard duplicates.
- **Why browser print?** Explicit recruiter action uses native printing/Save as PDF,
  avoiding another PDF service while retaining report traceability; physical print
  cancellation/layout acceptance must still be demonstrated.

Next viva question: **“Two candidate requests choose the same free interviewer slot:
why is checking availability without a transaction lock unsafe?”** Explain the race,
trace `interview_booking.py` and the self-scheduling router, then inspect synthetic
concurrency tests. Continue: ownership/invitations → F4 consent/source clocks → F11
run/epoch/final-only bridge → F5 citations → F6 freshness/confirmation → honest gaps.

## H. Remaining manual walkthrough

1. Open Interview Scheduling; explain active job, saved history and selection prerequisites.
2. Trace select → invitation/manual booking → ownership, overlap and duplicate errors.
   Do not send email or join media merely to explore navigation.
3. Explain F3/F4/F11 screens from saved safe evidence if optional services are disabled.
4. Open an authorized saved F6 report/comparison if available; distinguish missing,
   unscored, historical and restricted evidence. Do not create confirmations without approval.
5. Review print/PDF preview and cancellation only with approved synthetic data.
6. Rehearse a nine-minute account: architecture/job (1 min), intake/F1/F2 (2), F3
   concurrency (1.5), F4/F5 (1.5), F6 (1), F11 evidence/limitations (1), gaps (1).
   This is a proposed rehearsal allocation, not a verified full live demonstration.

## I. Home-only material and privacy boundary

Filename-only inventory found these outside Git in the older home checkout:

- `/home/shafi/Projects/TalentTrace-AI/data/home/viva/DEMO_AND_CODE_MAP.md`
- `/home/shafi/Projects/TalentTrace-AI/data/home/viva/F3_SCHEDULING_DEEP_DIVE.md`
- `/home/shafi/Projects/TalentTrace-AI/data/home/HOME-RECOVERY-REPORT.md`

Their contents were not read or copied for this task. They require an individual
privacy/staleness review before transfer. This was a targeted inventory of known
home/data roots, not a whole-home private-file search. Ignored benchmark results,
local UI screenshots, runtime settings, backups and database volumes are not part
of this portable handover. Do not transfer them automatically.

Transfer source through the private repository and this reviewed Markdown file.
Do not include `.env`, cookies, invitation links, account emails/passwords, browser
profiles, CVs, recordings, dumps or raw provider transcript text. No trainer
clarification document or new acceptance approval was supplied for this handover.

References: [release matrix](release_traceability.md) (historical checkpoint;
its older F11/N19 rows are superseded by later evidence),
[integration evidence](final_release_integration_20261020.md),
[synthetic F4/F11](f4_assemblyai_synthetic.md), [F2](f2_scoring.md),
[F3](interview_scheduling.md), [F6](f6_consolidated_assessment.md),
[F11 logic](f11_copilot_logic.md), [Milestone 3](milestone3_closure.md).
