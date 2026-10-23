# Screening outcome clarity

Based on integrated develop `480184c`, verified against origin on 23 October 2026.

## Confirmed behavior and correction

Existing batch models already preserve unique upload identities, processing errors,
eligibility decisions and score states. Persistence saves unscored states, and the
UI already renders unscored explanations and requirement evidence. No additional
ledger, response field, database migration or scoring change was needed.

The UI previously displayed an unconditional "Batch complete" heading and described
the eligible subtotal as complete scores, despite eligible-but-unscored candidates.
It now labels incomplete evaluations explicitly and separates numeric scores from
eligibility. The summary shows a reconciling equation across six disjoint groups:
scored, eligible unscored, excluded, eligibility review, source unavailable and
processing failures. Eligible is explicitly a subtotal, not another additive group.
Session-only coverage ranking remains distinct from persisted numeric-score ranking.
Only scored candidates appear in the latter; evidence disclosures remain unchanged.

## Offline verification

- Five new Node tests exercise a valid synthetic 20-application response (4 scored,
  11 eligible unscored, 4 excluded, 1 operational failure), one card per upload,
  reconciled totals, unchanged ties/ranks, unscored reasons, saved-score JSON reload,
  wrong-job/duplicate/count rejection, successful batches, review and unavailable sources.
- Focused Node suites: **36 passed**, zero failed/skipped (31 existing + 5 new).
  `node --experimental-strip-types --test frontend/tests/screening.test.ts frontend/tests/savedScores.test.ts`
- Existing Python scoring/ranking/route-persistence suites: **44 passed**.
  From backend: `python -B -m pytest tests/test_candidate_scoring.py tests/test_screening_ranking.py tests/test_score_integration.py -q`
  The persistence suite uses a transactional SQL double, not a live database.
- TypeScript app and Vite-config checks passed using `tsc -p tsconfig.app.json
  --noEmit` and `tsc -p tsconfig.node.json --noEmit` from frontend.
- An additional standalone TypeScript check of the two test files failed on ten
  pre-existing diagnostics in screening.test.ts lines 93–188 (React element typing,
  implicit mock parameters and criterion-array inference). All reported locations
  precede the new tests, which start after line 389. These unrelated test-typing
  issues were not changed; Node execution and production TypeScript checks pass.
- `vite build --configLoader runner` passed; existing >500 kB live-interview chunk
  warning remains. Runner avoids writing bundled configuration into shared dependency
  storage. Existing dependencies were reused; none installed or modified intentionally.
- Initial checks found a wrong Python working directory, a test header matcher issue
  and an edit-script encoding error; corrected before final validation.
- `git diff --check` passed. No browser acceptance or real benchmark was run.

## Scope limits

This is outcome accounting/presentation clarity, not complete F1/F2 acceptance.
The BID's all-screened-candidate ranking requirement remains a policy/implementation
gap. Uncertain evidence still causes deliberate abstention; scoring accuracy and
upstream model repeatability are not improved or newly verified. N1 remains PARTIAL:
this mocked/synthetic offline test is not a second measured 20-CV provider benchmark.
No providers, live databases, runtimes, F11 code or retained evidence were changed.
