# TalentTrace AI

> **Positioning Statement**: An evidence-backed interview intelligence platform that bridges automated CV screening with verifiable live conversation analysis to enable defensible, bias-free technical hiring decisions.

## Project Information
* **Programme**: AI Trainee Developer Programme — Final Evaluation Assignment
* **BID Reference**: Version 1.0 (Pages 1–34)
* **Author**: Shafi Mahmud

## Documentation Directory (/docs)
* [F11 Increment 5C: trusted recognized-speech adapter](docs/f11_copilot_live.md) — default off; automated integration verified, live Docker/browser gate blocked.
* [F11 Increment 5B: secure delivery and separate consent](docs/f11_copilot_delivery.md) — default off; internal synthetic events only, no live speech hook.
* [F11 Increment 5A: offline contextual co-pilot logic](docs/f11_copilot_logic.md) — logic only; not a live or completed Innovation Feature.
* [Isolated Docker synthetic startup and verification](docs/docker_startup.md)
* [F6 Increment 1: read-only consolidated candidate assessment](docs/f6_consolidated_assessment.md)
* [Milestone 3 closure: verified demonstration and remaining gaps](docs/milestone3_closure.md)
* [Project Naming & Positioning (P1.1)](docs/project_naming.md)
* [Requirement Clarifications (P1.2)](docs/clarifications.md) *(In progress)*
* [Work Breakdown Structure (P1.3)](docs/wbs.md) *(In progress)*
* [High-Level Architecture (P1.4)](docs/architecture.md) *(In progress)*
* [Risk Register (P1.5)](docs/risk_register.md) *(In progress)*

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
