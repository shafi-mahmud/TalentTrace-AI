# F5/F6 final synthetic acceptance — 27 October 2026

Branch: `feature/office-20261026-acceptance`. Inspected implementation baseline:
`ed16fd17989e18205417f1b04bb55af32ab8d97e`.

## Verdict and scope

- **F5: PARTIAL overall; current authenticated service integration PASS.** Real
  LangGraph, segmentation, mapping, curated references, grounding, durable storage
  and retrieval ran successfully with an explicit deterministic model double.
  No new real Groq inference or evaluation-quality acceptance is claimed. The
  historical actual Whisper-to-Groq PASS remains in [Milestone 3](milestone3_closure.md).
- **F6: PASS for this bounded synthetic application/report acceptance**, including
  combined evidence, same-job comparison, native print preview, restart retrieval
  and withdrawal. This is not full production/BID acceptance or a live STT-to-Groq
  interview demonstration.

No production defect was demonstrated. No application code, scoring formula,
combined-score policy, schema or provider fallback changed. Documentation only.

## Current architecture and exact identities

Implemented F5 entry points are the protected analysis config/start/status routes
in `backend/app/api/routers/interview_analysis.py`. The durable manager revalidates
owned finalized source and criteria revision before inference, commit and reads.
`InterviewEvaluationWorkflow` executes Pair → Map → Retrieve → Assess → Validate,
with conservative abstention and one bounded grounding repair. The reference
corpus is a versioned, curated official-documentation paraphrase; default retrieval
uses local alias matching, not a new web crawl or cloud embedding service.

F6 report/comparison routes in `consolidated_assessment.py` identify the exact
`(job_id, batch_id, upload_id)` and current revision. A booked application's F2
selection snapshot is retained rather than silently replaced by rerun scores.
F5 evidence is joined through the exact owned interview, source fingerprint and
revision. Missing/withdrawn interview evidence does not turn into a zero score.
No overall numeric score, automatic ranking or hire/reject recommendation is added.

## Preserved fixture and simulated boundaries

The original isolated project/database and named volume were reused after the
owner stopped the API and PostgreSQL containers. Container labels, volume and
schema `0017_booked_interview_email` were verified before restart. No migration,
fixture recreation or repeat of the 63-test suite occurred during resume.

The earlier fixture contains two fictional same-job applications with validated
fixture F2 scores, one booking, and two clearly synthetic, speaker-attributed turns.
Those turns were written through existing consent/persistence services as fixture
source; they are not actual ASR output. The existing graph's model interface alone
was replaced in the isolated process by `mock / offline-test-only`. No frontend
API response or recruiter authentication was mocked. External transport was denied.
The working Groq application, other runtimes and preserved databases were untouched.

## Verified workflow

| Boundary | Actual result |
| --- | --- |
| F5 browser start | Real recruiter login → saved job → booked interview → explicit analysis disclosure → authenticated start → completed operation. |
| Segmentation and grounding | One answered Q&A from two role/timestamped source turns; exact source quotations; four rubric dimensions; Python requirement coverage and conservative completeness gap. |
| Technical reference | One `python313-lists-v1` curated reference retrieved and cited; deterministic assessment passed the production grounding validator. Not model accuracy evidence. |
| F6 combined browser report | Correct revision 2, selection-time F2 coverage score, persisted F5 interpretations, strengths, gaps, source links and explicit no-combined-score notice. |
| Same-job comparison | Actual UI selected two distinct saved applications and called the authenticated comparison API. Application A had available F5 evidence; B was CV-only/not scheduled. Selection order and distinct identities were retained; absence was not negative performance. |
| Backend restart persistence | Owner stop/start of the same backend/database preserved the completed operation and exact result. Fresh authenticated F5/F6/comparison GETs passed. The model journal remained at one deterministic call. |
| Ownership/isolation | Wrong job/upload denied; duplicate comparison rejected; foreign recruiter F5/F6/comparison denied. Candidate-cookie-only requests to recruiter F5/F6/comparison returned 401. No candidate privacy capability was refreshed in resume. |
| Native print | Owner confirmed the complete native preview contained CV/F5/source material, then confirmed cancellation. Browser inspection found zero remaining temporary print copies. No PDF file or physical print was produced. |
| Withdrawal | Authenticated owning recruiter invoked the production withdrawal endpoint for this exact synthetic interview. Verified deletion, F5/transcript denial and F6 withdrawn-without-text all passed; F2 remained readable. |
| Physical deletion | Identity-scoped database checks found the original one analysis/two turns reduced to zero/zero. No unrelated record was targeted. |
| Browser privacy refresh | Fresh report showed the withdrawn notice, preserved CV evidence and no source transcript. |

Print/PDF copies already exported would be outside application revocation; this
check cancelled the preview and did not claim remote deletion of external copies.
Candidate access denials during resume do not claim a new live participant session
or exercise of a newly issued long-lived candidate deletion capability.

## Tests and evidence

- Before the pause: **63 backend passed / 17 optional skips** in the existing
  isolated, network-restricted Docker integration infrastructure at schema 0017.
  It included eight connected complete/incomplete/failure/epoch cases and focused
  Q&A, reference, evaluation and F6 tests. Optional home-PG/local-model gates stayed
  skipped. These tests were not rerun or double-counted during resume.
- Before the pause: **31 focused frontend tests passed**, covering combined reports,
  comparison, privacy redaction and print authorization/cleanup. Not rerun here.
- Resume: **13 real authenticated API/persistence/association checks passed** and
  **7 withdrawal/deletion/no-extra-inference checks passed**. Browser comparison,
  withdrawn report and temporary-print cleanup were inspected; native preview and
  cancellation were owner-observed.
- No production source changed; no unnecessary TypeScript/build or broad regression
  rerun was performed. Documentation whitespace and local-link checks passed.

Private locator: ignored `data/f5f6-current.json`. It points to the original
fixture, model-call journal, API/privacy results and synthetic browser screenshots.
No login values, private IDs, transcript text, screenshots or database artifacts
were copied into Git. The exact test-owned API, PostgreSQL and Vite process were
stopped after verification; the named volume and evidence remain. Groq container
identities/start times were unchanged. No LiveKit/AssemblyAI or paid API was called.

## Exact remaining acceptance limits

Current real-provider F5 evaluation quality and a full live F4 → F5 → F6 chain were
not rerun; combined live F4 remains PARTIAL. Broad question pairing/reference-topic
coverage and optional semantic retrieval are not certified by a two-turn fixture.
Native PDF file output, physical printing and exhaustive pagination/device coverage
remain unverified. No approved combined numeric suitability formula was invented.
Full non-synthetic/production authorization, operational scaling and retention of
external report copies remain separate. No F11 work, clean-machine Docker closure,
merge or push was started.
