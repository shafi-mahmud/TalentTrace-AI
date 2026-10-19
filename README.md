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
N1 still lacks the required measured 20-CV end-to-end benchmark in this README.
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
