# F2 scoring foundation

## Implemented

`schemas/candidate_score.py` and `services/candidate_scoring.py` provide an
deterministic score from existing server-validated Screening results.
No new matching, provider calls, workflow or candidate contact fields.
The authenticated batch-screening API now calculates scores server-side after
the existing workflow. The UI displays weighted scores, dimension breakdowns,
original explanations/provenance, explicit ties and separate not-scored outcomes.
The existing requirement-count ranking remains in the API; the F2 UI uses the
additional eligible-only score ranking. Hard-requirement decisions are unchanged.

Weights are strict integer percentages for skill, experience and education,
bounded 0–100 and totaling 100. Callers can supply `ScoringWeights`; provisional
defaults are 50/30/20. They are **assumptions**, not confirmed BID weights.

Within each dimension, supported criteria count equally, whether deterministic
or semantic. Coverage is supported / confirmed criteria; contribution is that
fraction multiplied by its configured weight. Sum unrounded contributions, then
round half-up to two decimal places. Breakdown percentages and points are rounded
for display and may differ from their rounded sum by 0.01. For example, 50% skill
coverage, 100% experience and 0% education produce 55 with default weights.

Eligibility remains separate: only completed eligible results are scored.
Excluded/insufficient-evidence results, parsing/source/provider failures and
ambiguous evidence in a positive-weight dimension receive `not_evaluated` and
null score, not zero. A positive-weight dimension with no reviewed criterion also
has no score; weights are never silently redistributed. A recruiter may explicitly
configure zero weight for an unused dimension. A complete eligible candidate with
all criteria not demonstrated has a genuine zero coverage score.

The breakdown preserves original requirement explanations, evidence and digital/OCR
source references. Not-found evidence is described as not demonstrated, never proof
that a person lacks a qualification. Citations establish provenance, not guaranteed
semantic correctness. This score measures validated requirement coverage, not hiring
success or overall human suitability. No automatic hiring decision is added.

The shared snapshot validator rechecks result schemas, job reference, criterion IDs,
categories and hard flags. Callers must supply the current server-confirmed snapshot;
the existing result contract does not encode criterion-description revisions.
No public client-supplied score/result endpoint is introduced.

## Implemented integration; live synthetic verification completed

Recruiters edit integer weights in Candidate Screening and confirm them with the
criteria. Editing either invalidates local approval/results while retaining uploaded
CVs. The existing owner-protected `PUT /api/v1/jobs/{job_id}/criteria` validates and
saves weights, increments the job revision and records explicit confirmation.
The frontend sends `X-TalentTrace-Job-Revision` when screening; stale revisions are
rejected before provider execution. Older clients without the header use current
server-approved weights, not client scores.

Migration `0003_candidate_scores` adds job weights and `candidate_scores`. Each
record belongs to a job, batch, upload, criteria revision and `f2-coverage-v1` scoring
version. Batch/upload identities refer to existing private filesystem intake,
not invented database candidate/upload tables. Records store original validated
evidence, no contact fields. They are still privacy-sensitive: protect database
access/backups and apply the project's retention policy before production use.

The job row lock prevents edits during screening and serializes same-run writes.
All candidates persist in one transaction; reruns replace only that exact
job/batch/revision/version. Historical revisions remain. Owned
`GET /api/v1/jobs/{job_id}/batches/{batch_id}/scores` reads only the current approved
revision, validates stored payloads and returns safe errors for invalid records.
The UI can reload those saved scores while the matching batch evidence is present.
Restoring the whole upload/screening workspace after a browser restart is **Planned**.

**Verified by automated tests:** calculation/rounding, weights, exclusions,
uncertainty, source errors, ties, owner isolation, approval/stale revision checks,
JSON payload round-trip, corrupted-record rejection, response consistency and UI
runtime validation/rendering. API persistence tests use a transaction-capable SQL
double. On 12 October 2026, a migration-default defect was corrected: PostgreSQL
`jsonb_build_object` avoids SQLAlchemy interpreting numeric JSON colons as binds.
The actual base-to-head upgrade passed on a fresh disposable pgvector PostgreSQL
database, including server default 50/30/20, invalid-weight rollback, downgrade to
0002 and re-upgrade. The temporary container was removed; the office demo database
was not migrated.

On 12 October 2026, F2 was verified against another new isolated PostgreSQL database
using actual HTTP routes and configured Groq providers: recruiter login, approved
criteria/weights, synthetic DOCX/PDF intake, screening, score write/read, stale
revision and cross-recruiter denial passed. A strong candidate scored 100; weaker
ambiguous evidence correctly remained unscored, exclusion stayed separate, and a
blank CV had no decision/score. Browser checks covered confirmation, upload,
breakdown/source evidence, saved-score reload and approval invalidation preserving
the batch. A separate actual LangGraph/BGE/pgvector/Groq JD request returned 200
with three validated policy citations. Fractional/lower scores and ties were
tested automatically, not observed live. Temporary services/container were removed.

**Recommended manual verification:** back up/choose an isolated development DB,
inspect Alembic current revision, explicitly approve and apply `alembic upgrade head`
with the existing backend environment. Start isolated F2 backend/frontend ports;
leave the preserved demo untouched. Sign in as a provisioned recruiter, confirm
criteria/weights, upload synthetic CVs and screen. Check eligible scores/ties,
not-scored reasons, original OCR evidence, unchanged exclusions and reload saved
scores. Edit weights and verify re-confirmation is required. Another recruiter
must receive 404 for the owned job's score endpoint. Do not publish to Discord.

## Documented references and assumptions

README references BID v1.0 and `docs/wbs.md`, but the BID and WBS scoring rules were
not available in this local checkout during implementation. No numeric weights,
partial-credit rule, mandatory weighting or task identifier could be verified.
Defaults, equal per-criterion credit, conservative ambiguity handling and missing-
dimension behavior therefore require trainer/product review before evaluated use.
An atomic criterion does not gain partial credit from vague similarity.

## Recommended progress note — not applied to WBS/Redmine

F2 scoring foundation and API/UI integration implemented: reviewed job-bound weights,
server-calculated 0–100 coverage, source-backed breakdown, conservative no-score
handling, owner-protected persistence/read APIs and eligible-only score ranking.
Automated, isolated migration/persistence and synthetic browser checks passed.
Do not mark evaluated F2 complete before policy/formula review. No Redmine percentage,
task identifier or trainer-owned WBS was modified.

## Next recommended increment

Confirm BID/WBS scoring policy with the trainer. F3's first provider-independent
selection/scheduling increment is described in [interview scheduling](interview_scheduling.md).
