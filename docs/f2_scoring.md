# F2 scoring foundation

## Implemented

`schemas/candidate_score.py` and `services/candidate_scoring.py` provide an
internal deterministic score from existing server-validated Screening results.
No new matching, provider calls, workflow, tables or candidate contact fields.
The current batch API, UI, requirement-count ranking and eligibility policy are
unchanged. This is a foundation, not a connected scoring demonstration.

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

## Documented references and assumptions

README references BID v1.0 and `docs/wbs.md`, but the BID and WBS scoring rules were
not available in this local checkout during implementation. No numeric weights,
partial-credit rule, mandatory weighting or task identifier could be verified.
Defaults, equal per-criterion credit, conservative ambiguity handling and missing-
dimension behavior therefore require trainer/product review before API/UI adoption.
An atomic criterion does not gain partial credit from vague similarity.

## Recommended progress note — not applied to WBS/Redmine

F2 candidate-scoring foundation implemented and tested internally: configurable
weights, bounded deterministic score, source-backed breakdown and no-score failure
handling. Eligibility and Milestone 1 ranking unchanged. Do not mark F2 complete:
approved formula/weights, job-bound weight review, API/UI integration, durable score
records and live synthetic demonstration remain **Planned**. No Redmine percentage
or trainer-owned WBS was modified.

## Next recommended increment

Confirm scoring policy, then attach reviewed weights to the job snapshot and expose
validated scoring alongside screening in one bounded API/UI increment. Preserve
existing rank ordering until a separate approved policy specifies score-based order.
