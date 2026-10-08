# Candidate Screening foundation — #647495

## Implemented — preparation only

`backend/app/agents/screening/workflow.py` contains a bounded, multi-node
LangGraph workflow. It has no API or frontend integration yet. Its async
`CandidateScreeningWorkflow.prepare()` method returns a validated preparation
result, not an eligibility verdict.

### Inputs and state

`ScreeningInput` accepts the existing syntactic demo Job Reference, an opaque
upload UUID, the existing `parsed` / `source_unavailable` / `parsing_failed`
semantics, `CandidateQualifications` and 1–50 explicitly supplied criteria.
The demo reference is not proof of a persisted or approved job; the upload UUID
is not resolved against storage in this increment.

Each criterion has a safe 1–64-character ID, category `skill`, `experience` or
`education`, a nonblank single-line description of at most 500 characters and
a strict boolean `is_hard`. There are only hard and non-hard requirements.
Duplicate IDs are rejected case-insensitively; unknown fields are forbidden.
Parsed input requires qualifications, including valid empty lists; failed or
unavailable input requires null qualifications.

Typed state contains only the request, grouped requirement context, source
readiness and preparation result. Contact data, protected-attribute fields and
raw CV text are not accepted. Qualifications retain existing page/block and
digital/OCR locators. This workflow assumes a trusted internal caller passes
the existing parser's validated output: it cannot independently prove grounding
without the original evidence and does not re-extract or call Groq.

### Nodes, edges and conditional routing

```text
START -> validate_screening_input -> prepare_requirement_context
      -> check_candidate_source
         ready       -> build_ready_result              -> END
         unavailable -> build_source_unavailable_result -> END
```

- `validate_screening_input` revalidates the request and nested qualifications,
  including potentially mutated upstream lists.
- `prepare_requirement_context` groups criterion IDs by category in input order
  and identifies hard-requirement IDs. It makes no satisfaction decisions.
- `check_candidate_source` checks parsed status and qualifications availability,
  independently of whether skills or other qualification lists are empty.
- The two result nodes build validated `ready_for_matching` or
  `source_unavailable` results with identifiers, original parsing status and
  requirement context. `screening_decision` is always null; matching results,
  scores and final verdict fields are not present.

This is a workflow rather than another parser: it prepares requirements and
routes downstream work by source readiness. Named nodes and a conditional edge
provide explicit extension points. Source failure is not missing qualifications;
empty skills do not mean exclusion. `ready_for_matching` means ready for a future
step, not eligible, verified or suitable.

### Privacy and boundaries

Contact identity is excluded because it is not a merit signal. Typed field
exclusion is not a semantic detector for personal information placed inside
free-text criteria or qualification values; trusted callers must keep these
inputs appropriate. No content is logged, persisted or sent to an external
service. No candidate RAG, matching, ranking, scoring, Groq call or checkpoint
integration exists here. Use synthetic data for current verification.

## Planned — next WBS tasks

- **#647496:** extend the ready branch with semantic attribute matching that
  retains evidence provenance; candidate qualifications must not enter RAG.
- **#647497:** evaluate verified hard requirements and implement the planned
  three-way outcomes. No such final decision is produced now; unavailable
  evidence must not be converted into automatic rejection.
- **#647498:** integrate the existing PostgreSQL checkpoint foundation with
  validated workflow/thread identity. This graph currently compiles with
  `checkpointer=False`; persistence and resumability are not claimed.

Authentication, approved-job persistence, API/UI integration and production
privacy controls remain separate work. Tests exercise the real graph using
synthetic inputs, including both conditional paths and absent decisions.
