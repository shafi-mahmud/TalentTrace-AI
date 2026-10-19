# TalentTrace AI

> **Positioning Statement**: An evidence-backed interview intelligence platform that bridges automated CV screening with verifiable live conversation analysis to enable defensible, bias-free technical hiring decisions.

## Project Information
* **Programme**: AI Trainee Developer Programme — Final Evaluation Assignment
* **BID Reference**: Version 1.0 (Pages 1–34)
* **Author**: Shafi Mahmud

## Pre-viva release-candidate checkpoint — 19 October 2026

**PARTIAL BID acceptance.** Proposed code base: `176ba82` on
`feature/f11-copilot-live-integration`. This documentation checkpoint does not
activate features, migrate data or publish a release.

- [Release inventory and validation gates](docs/release_candidate_checkpoint.md)
- [BID requirement-to-evidence matrix](docs/release_traceability.md)
- [Innovation Feature: Dynamic Interviewer Co-Pilot — rationale](docs/f11_innovation_rationale_draft.md)

F11 is implemented through the trusted live adapter and automated integration;
physical speech-to-suggestion acceptance remains pending. The rationale documents
AI assistance and does not establish originality or independent-design compliance. N19 remains
PARTIAL and its administrative tooling exists only on the separate N19 branch.
N1 now has a measured 20-input attempt below, with PARTIAL completion; it is not
a successful 20-CV scoring/ranking acceptance result.
N21 has office baseline startup evidence, not full clean-machine acceptance.

## Documentation directory

- [F11 current integration and historical test evidence](docs/f11_copilot_live.md)
- [F11 delivery and independent consent](docs/f11_copilot_delivery.md)
- [F11 model-free contextual logic](docs/f11_copilot_logic.md)
- [Docker setup and its full-application acceptance gap](docs/docker_startup.md)
- [F6 consolidated assessment and reviewer confirmation](docs/f6_consolidated_assessment.md)
- [Controlled Milestone 3 closure](docs/milestone3_closure.md)
- [Product identity](docs/project_naming.md)
- [Architecture diagrams and ADRs](docs/architecture/)
- [Risk register](docs/risk_register.md)
- [Interview access and self-hosted token limitation](docs/interview_invitations.md)

The previously linked `docs/clarifications.md`, `docs/wbs.md` and
`docs/architecture.md` are absent. Their links have been removed rather than
creating invented trainer clarifications or a substitute official WBS. Architecture
PDFs are design records; implemented behavior must be checked against code.

## N1 benchmark — 20 synthetic CVs, PARTIAL (19 October 2026)

Tested source: `b3c00db89aec0f891b039e32a065ec36c2e44ec6`. One actual authenticated
FastAPI batch used local PDF extraction, real free-tier Groq
`openai/gpt-oss-120b` profile/semantic inference, LangGraph screening, unchanged
50/30/20 weighted scoring, ranking and PostgreSQL persistence. No mocks or fixed
scores. Hardware: Intel Core i5-10210U, 4 cores/8 logical processors, approximately
15.84 GiB visible RAM; Windows/Python 3.12, disposable Docker PostgreSQL17/pgvector.

| Measurement | Actual result |
| --- | --- |
| Input / parsed profiles | 20 / 20 synthetic digital PDFs |
| Screening decisions / operational failures | 19 / 1 terminal HTTP429 |
| Eligible / excluded | 15 / 4; failed candidate has no decision |
| Numeric scores / score ranking | 4 / 4 |
| Other score states | 11 uncertain evidence, 4 ineligible, 1 incomplete |
| Eligible requirement-coverage ranking | 15; distinct from numeric-score ranking |
| Total wall time | **449.09 seconds (7m29.09s)** |
| Upload / screen-through-persistence | 0.18 / 448.91 seconds |
| Logged profile stage / screening stage | 273.33 / 174.80 seconds |
| Submitted-input throughput | 2.67 CVs/minute; not successful-score throughput |
| Rate-limit recovery | 36 bounded backoffs; 328 seconds waiting included |

Timing starts before the multipart upload and ends after the single screening
response, including score persistence and ranking. It excludes environment setup,
fixture generation, login/job approval and retrieval verification. API requests
used the real FastAPI ASGI transport rather than a network server/browser, so
network/proxy overhead is excluded. No model prompts used expected fixture answers.

All 20 revisioned score-state records were retrieved from PostgreSQL and matched
the response. Numeric ranking is reconstructed from persisted scores, not stored
as an independent ranking snapshot. All 19 completed mandatory-Python decisions
matched the original synthetic facts. Conservative uncertainty was preserved;
no screening failure was converted into rejection or a fabricated score.

Reproduce with a fresh disposable database/storage, explicit migrations and
administrative fictional recruiter provisioning; authenticate; create a manual
job and confirm criteria; upload 20 PDFs; call the owned batch `/screen` endpoint
once; retrieve `/jobs/{job_id}/batches/{batch_id}/scores`. The fictional job used
mandatory Python, optional SQL, minimum 2 years relevant experience and BSc Computer
Science. Inputs vary skill presence, 1–6 years experience and degree presence.
Reproduction requires separately approved free provider access and sufficient
quota. Exact synthetic PDFs, hashes, fixture-generation/API scripts, sanitized
timings and resource samples are retained locally under ignored `data/n1-20-cv/`;
they are not shipped in Git, so this README is not a self-contained benchmark kit.

This is **PARTIAL N1 evidence**, not full 20-CV completion: only 4 numeric scores
were produced, 11 eligible applications remained uncertain and one screening
failed after existing retry limits. Ineligible candidates remain excluded from
displayed rankings. Small digital synthetic PDFs do not establish scanned-CV,
long-document, semantic accuracy, repeated-run stability or all-candidate ranking
acceptance. No automatic second attempt was made.

## Isolated Docker startup — synthetic development

Requires Docker with Linux containers, Compose v2+, and Python 3.10+ on the host
only for the private-configuration helper. Run from the repository root:

```text
python docker/configure.py
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env build
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env up -d --wait db
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env run --rm --no-deps backend python -m alembic upgrade head
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env up -d --wait --wait-timeout 180
```

Open **http://127.0.0.1:5188/**. First setup starts with an empty, separate
database. No accounts, jobs or candidate records are seeded. Provision a synthetic
recruiter explicitly when ready:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env exec backend python -m app.db.provision_recruiter
```

Subsequent startup is one command, preserving named volumes:

```text
docker compose -p talenttrace-docker-demo --env-file data/docker-demo.env up -d --build --wait --wait-timeout 180
```

This is a local synthetic baseline, not production or a full clean-machine BID
acceptance claim. It keeps SMTP, LiveKit, captions/storage, F5 inference and reviewer
confirmation disabled. No private office environment, model or data is copied.
The internal network prevents backend/database Internet access. See the setup guide for
readiness, stop/reset boundaries, tests and limitations before using other features.
