# F1/F2 deadline acceptance review

Reviewed from integrated develop `48f804f4f20e81a743126e930ad1149de0ce78f1`.
This increment adds offline acceptance coverage and corrects the evidence record;
it changes no scoring formula, matching policy, production service or database.

## Verified requirement boundary

The locally available official BJIT BID, page 12, requires F1 batch extraction,
semantic matching, an ordered ranking of all screened candidates, CV-backed
reasoning and safe imperfect-input handling. F2 requires skill, experience and
qualification dimensions, configurable weights, aggregate/breakdown/justification,
repeatability and retrievable scores. Page 18 N1 requires a measured 20-CV
parse/screen/score/rank window. It specifies no 50/30/20 formula or automatic
partial-credit rule.

The owner-supplied mandatory-requirement clarification is recorded in
[candidate_screening.md](candidate_screening.md#implemented--trainer-approved-hard-requirement-policy-647497):
a mandatory qualification not demonstrated causes exclusion; ambiguous mandatory
evidence requires review. This review used that retained clarification, not a new
independent trainer confirmation. The clarification does not establish a policy
for assigning numeric ranks to excluded, uncertain or failed applications.

| Requirement | Implemented and verified in this increment | Remaining acceptance |
| --- | --- | --- |
| F1 eligibility and evidence | Real screening graph and mandatory gate, exact and synthetic semantic outcomes, original evidence and source references | Actual semantic correctness, extraction robustness across layouts/scans |
| F1 ranking | Deterministic eligible requirement-coverage ranks; scored-only weighted ranks | BID all-screened-candidate ranking is still unsupported; no invented ordering policy |
| F2 arithmetic | Existing 50/30/20 arithmetic, ties, abstentions and identical-input repeatability | Formula/default policy review; repeated model inference accuracy/stability |
| F2 retrieval/security | Actual authenticated routes, ownership/revision/batch checks and persistence/reload services over a transactional SQL double | This run is not PostgreSQL or browser acceptance |
| N1 throughput | Historical measured attempt remains documented in README | No new provider benchmark; full 20-CV numeric scoring/ranking not established |

## Retained October 19 benchmark: established cause of abstention

Read-only inspection found the retained manifest, 20 synthetic PDFs, complete
batch response and measurement files. All 20 PDF hashes matched their manifest.
No private artifact was copied into this branch or committed.

The approved criteria were mandatory Python, preferred SQL, minimum two years
relevant experience and Bachelor of Science in Computer Science; weights were
50% skill, 30% experience and 20% education. The response contains 15 eligible,
four excluded and one matching failure. All 11 eligible unscored results contain
ambiguous **experience** matches; one also contains ambiguous **education**.
All 12 ambiguous matches were semantic results with the existing generic
insufficient-evidence explanation, not the cross-record education safeguard.

`score_candidate()` deliberately returns `uncertain_evidence` if any requirement
in a positive-weight dimension is ambiguous. Thus the 30% experience weight
blocks all 11 numeric scores; the 20% education weight also applies to one of
them. The particular 50/30/20 proportions are not an arithmetic defect: the
positive-weight ambiguity gate would still apply with other positive weights.
Only an explicitly approved zero weight excludes a dimension from that gate;
this review does not recommend changing weights merely to obtain more scores.

Current code recomputed all 20 saved score states and the exact four-entry numeric
ranking from retained validated matching results. JSON arrays/UUID strings were
explicitly restored to the existing strict tuple/UUID contract for this local
audit; the initial direct response-model decode failed that type contract. No
validation rule was weakened. This establishes deterministic downstream scoring
consistency, not why the model regarded the experience evidence as ambiguous.
No deterministic matching or evidence-association defect causing the 11
abstentions was demonstrated. Stored outputs alone do not establish that the
upstream parser or semantic decision was correct.

The files permit offline scoring/ranking recomputation and input hash checks.
They do not reproduce Groq inference, rate limits, extraction/profile outputs or
the historical 449.09-second performance. No provider/API script was executed.

## New committed acceptance coverage

`backend/tests/test_f1_f2_deadline_acceptance.py` supplies 20 newly constructed,
contact-bearing fictional profiles to the normal batch service and real screening
graph. An explicit semantic double supplies reviewed test outcomes. It does not
infer qualifications or pretend to be Groq. Four eligible scores are calculated
as **100, 100, 55, 25** with ranks **1, 1, 3, 4**; 11 eligible applications remain
unscored, four are excluded and one has a terminal matching failure.

The connected test uses real login, job confirmation, ownership/CSRF checks,
screening/scoring routes, validators and score persistence/reload services. Only
profile extraction, semantic interpretation and SQL execution are substituted.
It verifies all 20 upload identities occur once, evidence/justifications and OCR
references survive scoring, contact sentinels never enter responses, saved results
equal initial results, another recruiter/job/batch cannot load them, exact reruns
replace rather than duplicate records, and a revised job cannot load or execute
the stale revision. A second test verifies positive-weight ambiguity abstention
and the existing explicit-zero-weight behavior without changing eligibility.

Source-retention limit: the initial batch retains ambiguous matching evidence.
Saved scored rows retain their dimension evidence; saved unscored rows contain a
decision/reason and no dimension evidence. This test does not establish later
retrieval of the full historical unscored matching result after the batch is lost.

The existing frontend 20-application rendering/reload tests independently verify
category reconciliation, one card per application, fixed unscored explanations,
partial-failure headings and no fabricated numeric score/rank. Their fabricated
presentation payload is not a replay of the new backend fixture or Groq outputs.

## Validation and limits

- Focused backend invocation: **201 passed, zero failed/skipped/deselected**,
  including the two new tests. SQL execution used existing doubles; no database
  was provisioned or modified.
- Focused frontend screening/saved-score invocation: **36 passed, zero
  failed/skipped**. Counts are separate invocations, not a benchmark.
- Production application and Vite configuration TypeScript checks passed; the
  production frontend build passed (76 modules, existing >500 kB interview chunk
  warning). TypeScript build metadata was written only to this worktree's ignored
  validation directory. Test-file typechecking was not part of these production
  checks; the Node tests executed directly.
- Initial frontend checking used an incomplete existing dependency tree without
  `livekit-client`; it failed before build. The isolated worktree then reused an
  already installed compatible tree through an ignored junction, without changing
  any dependency installation or another worktree's source.
- `git diff --check` passed. No live provider, browser, throughput or preserved-
  database acceptance was executed. Initial direct retained-response decoding
  and the first incomplete-dependency TypeScript invocation failed as described
  above; neither was concealed as a passing check.

**Recommended next acceptance task:** review the 11 synthetic experience cases
against their original CV evidence with the trainer/product owner and approve an
explicit policy for abstentions and all-screened-candidate ordering. Do not assign
zeros, infer partial credit or claim all-candidate numeric ranking to satisfy the
deadline. After that policy decision, a separately authorized provider repeatability
and complete 20-CV run is still required for full F1/F2/N1 acceptance.
