# TalentTrace AI Risk Register

Redmine **#647115 — Risk Register** is the authoritative operational risk tracker.
This file is its durable repository summary, using the owner-supplied Redmine
snapshot and repository evidence. **Last reviewed: 07 Oct 2026.**

## Risk-management principles

- Distinguish **Implemented** mitigations from **Planned** mitigations; documentation alone does not prove implementation.
- Treat hiring data as privacy-sensitive. Use synthetic/sample data for the current demo; do not claim production privacy compliance.
- Extraction failure is not evidence of a missing qualification or a reason to reject a candidate.
- LLM structured output validates shape, not factual truth. Source/evidence validation establishes textual support, not real-world accuracy.
- Keep candidate content untrusted and validate source/evidence before using extracted attributes.
- Exclude protected attributes from future scoring; screening/scoring is not implemented by the CV parsing foundation.
- Keep risks open until remaining exposure is genuinely addressed; feature completion alone does not resolve a risk.

## Current risk register

Status and progress below are the supplied Redmine snapshot, not newly calculated assessments.

| Redmine ID | Area | Risk | Status | Progress | Remaining exposure |
| --- | --- | --- | --- | --- | --- |
| #647119 | Feature 2.2 | PostgreSQL LangGraph checkpointer persistence and resumability | Resolved | 100% | Individual workflows still need checkpoint wiring. |
| #647120 | Feature 2.2 | Docker Compose startup and persistent-volume reliability | In Progress | 20% | Production Compose, named volumes, clean-machine startup, health checks and full restart/persistence verification. |
| #647150 | Feature 3.1 | Company Policy RAG retrieval quality and safe policy handling | In Progress | 70% | Retrieval evaluation, relevance threshold, policy lifecycle/version governance and persistent approval/revision. |
| #647717 | Feature 3.3 | Candidate PII exposure through CV processing and external LLM provider | In Progress | 40% | Authentication/authorization, consent/privacy governance, provider governance, retention/deletion and production audit controls. |
| #647719 | Feature 3.3 | Malicious CV content and prompt injection during candidate parsing | In Progress | 50% | Preserve the trust boundary in future Screening/Scoring; prompting does not eliminate injection. |
| #647720 | Feature 3.3 | OCR and extraction errors causing missing or incorrect candidate evidence | In Progress | 60% | Scan quality, complex-layout reading order, heuristic misclassification and absent correction/confidence workflows. |
| #647721 | Feature 3.3 | Private CV storage, retention and unauthorized access | In Progress | 40% | Access controls, retention/deletion, storage governance, Windows ACL review, private Docker volumes and audit controls. |

## Detailed risk notes

### Feature 2.2 — Database Models & Docker Compose

Redmine risk group: **#647116 — Feature 2.2: Database Models & Docker Compose — Risks**.

#### #647119 — PostgreSQL LangGraph checkpointer persistence and resumability

- **Risk:** Workflow state could be lost or resume incorrectly after a process restart.
- **Implemented mitigations:** Official `AsyncPostgresSaver`, a separate PostgreSQL checkpoint database, strict serialization, explicit setup and validated workflow/thread namespaces. Genuine cross-process interrupt/resume verification is documented in [checkpoint storage](checkpoint_storage.md).
- **Remaining exposure:** Individual workflows still need checkpoint wiring as they are implemented. The resolved infrastructure risk does not imply that every business workflow is resumable.

#### #647120 — Docker Compose startup and persistent-volume reliability

- **Risk:** Deployment startup or restarts could fail or lose persistent data.
- **Implemented mitigations:** PostgreSQL 17 with pgvector validated locally; migrations and RAG tested against PostgreSQL; LangGraph checkpoint persistence verified.
- **Remaining exposure — Planned:** Production `docker-compose.yml`, named volumes, clean-machine startup, service health checks and full restart/persistence verification. Local validation does not prove production deployment reliability.

### Feature 3.1 — Job Description Agent & Job Profile Setup

Redmine risk group: **#647139 — Feature 3.1: Job Description Agent & Job Profile Setup — Risks**.

#### #647150 — Company Policy RAG retrieval quality and safe policy handling

- **Risk:** Irrelevant, unsafe or obsolete policy context could produce misleading job descriptions.
- **Implemented mitigations:** Dedicated Company Policy RAG, an explicitly configured policy document UUID, BGE-small with PostgreSQL/pgvector semantic retrieval, bounded top-k, citation allowlisting, no silent lexical fallback and human review required. External policy ingestion is implemented; retrieved text remains untrusted reference data. See [project structure](project_structure.md) and [policy ingestion](company_policy_ingestion.md).
- **Remaining exposure — Planned:** Formal retrieval evaluation, a relevance-threshold decision, production policy lifecycle/version governance and persistent approval/revision. Semantic retrieval and citations alone do not guarantee relevant or correct drafts.

### Feature 3.3 — CV Intake, Extraction, OCR & Candidate Parsing

Redmine risk group: **#647715 — Feature 3.3: CV Intake, Extraction, OCR & Candidate Parsing — Risks**.
Implementation boundaries and verification are described in [CV ingestion](cv_ingestion.md).

#### #647717 — Candidate PII exposure through CV processing and external LLM provider

- **Risk:** Sensitive candidate information could be disclosed during storage, processing or external provider use.
- **Implemented mitigations:** Private CV storage; no original filenames/private paths in responses; raw extraction/OCR text is not persisted; candidate data is isolated from JD/RAG/MCP; Groq credentials are server-side. The current demo requires synthetic/sample data only. Candidate parsing sends CV-derived text to Groq and the UI discloses that transfer.
- **Remaining exposure — Planned:** Authentication/authorization, consent/privacy disclosure and governance suitable for real data, provider governance, retention/deletion and production audit controls. The existing demo disclosure is not production privacy compliance.

#### #647719 — Malicious CV content and prompt injection during candidate parsing

- **Risk:** Document instructions could manipulate extraction or influence later hiring decisions.
- **Implemented mitigations:** CV content is treated as untrusted data; Groq output is structured and validated; copied evidence and source IDs undergo deterministic source/evidence validation. Candidate text cannot select tools, models, job requirements or scoring. Unsupported extracted values fail validation.
- **Remaining exposure:** Preserve the same trust boundary in future Screening/Scoring. Prompt injection is not eliminated by prompting alone; textual support does not prove truth or correct semantic classification.

#### #647720 — OCR and text-extraction errors causing missing or incorrect candidate evidence

- **Risk:** Missing or incorrect text could misrepresent qualifications or supporting evidence.
- **Implemented mitigations:** Page/block evidence, explicit `ocr_required`, Tesseract fallback, digital/OCR provenance, controlled failure states and bounded resource limits. Real synthetic OCR verification is documented; failure is not treated as a missing qualification.
- **Remaining exposure:** Scan-quality dependence, complex-layout reading order and heuristic misclassification. Human correction workflows and confidence scoring remain **Planned**.

#### #647721 — Private CV storage, retention and unauthorized access

- **Risk:** Stored CVs could be accessed without authorization or retained beyond an appropriate period.
- **Implemented mitigations:** Private ignored storage, opaque UUID filenames, no static/download endpoint and path/symlink/storage-boundary validation. The current demo requires synthetic/sample data only; ignore rules are not an access-control mechanism.
- **Remaining exposure — Planned:** Authentication/authorization, retention/deletion, encryption/storage governance, Windows ACL review, Docker private-volume integration and production audit/access controls.

## Review and maintenance

- Update this summary when a material risk changes; the Redmine task remains the authoritative status/progress record.
- Do not mark a risk resolved merely because its related feature is implemented. Record verification and remaining exposure separately.
- Add future risk groups when Screening/Scoring, Interview, Post-Interview Evaluation, authentication, persistence or production deployment materially introduce risks. Use actual assigned Redmine IDs; do not invent them.
- Keep secrets, real candidate data, private file paths and credentials out of this document.
