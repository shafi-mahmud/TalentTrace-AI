# Candidate Screening foundation — #647495 and #647496

## Implemented — preparation and hybrid evidence matching

`backend/app/agents/screening/workflow.py` contains a bounded, multi-node
LangGraph workflow. It has no API or frontend integration yet. Its async
`CandidateScreeningWorkflow.prepare()` method returns a validated preparation
result, not an eligibility verdict. `match()` uses the same graph in matching mode
and returns requirement-level evidence statuses. Preparation behavior is preserved;
matching is an internal interface, not a new endpoint or frontend feature.

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
readiness and result, plus matching facts, unresolved criteria and intermediate
matching results when matching is requested. Contact data, protected-attribute fields and
raw CV text are not accepted. Qualifications retain existing page/block and
digital/OCR locators. This workflow assumes a trusted internal caller passes
the existing parser's validated output: it cannot independently prove grounding
without the original evidence and does not re-extract. Semantic matching may call
Groq using qualifications only, as described below.

### Nodes, edges and conditional routing

```text
START -> validate_screening_input -> prepare_requirement_context
      -> check_candidate_source
         unavailable -> build_source_unavailable_result -> END
         ready, prepare mode -> build_ready_result       -> END
         ready, match mode -> match_direct_evidence
           unresolved -> interpret_unresolved_requirements
                      -> validate_matching_evidence -> build_matching_result -> END
           all resolved -> validate_matching_evidence -> build_matching_result -> END
```

- `validate_screening_input` revalidates the request and nested qualifications,
  including potentially mutated upstream lists.
- `prepare_requirement_context` groups criterion IDs by category in input order
  and identifies hard-requirement IDs. It makes no satisfaction decisions.
- `check_candidate_source` checks parsed status and qualifications availability,
  independently of whether skills or other qualification lists are empty.
- The preparation result nodes build validated `ready_for_matching` or
  `source_unavailable` results with identifiers, original parsing status and
  requirement context. `screening_decision` is always null; matching results,
  scores and final verdict fields are not present in preparation results.
- `match_direct_evidence` assigns request-local fact IDs to selected qualification
  attributes, compares reliable direct values and retains unresolved criteria.
- `interpret_unresolved_requirements` invokes an injected semantic matcher once,
  only when necessary. Missing configuration, provider failure or invalid output
  is a controlled failure rather than a negative evidence conclusion.
- `validate_matching_evidence` checks criterion coverage and fact/value references,
  then restores original criterion order. `build_matching_result` assembles the
  validated evidence result or a separate failure state.

This is a workflow rather than another parser: it prepares requirements and
routes downstream work by source readiness. Named nodes and a conditional edge
provide explicit extension points. Source failure is not missing qualifications;
empty skills do not mean exclusion. `ready_for_matching` means ready for a future
step, not eligible, verified or suitable. Matching adds explicit deterministic,
semantic and validation stages to that existing workflow, not another agent.

### Deterministic and semantic boundary

The deterministic rule compares the **entire** criterion description with an
appropriate fact value after NFC normalization, case folding, whitespace collapse
and removal of one terminal full stop. Meaningful punctuation is preserved:
`Java` does not equal `JavaScript`, and `C` does not equal `C++`. There are no fuzzy
matches, inferred skills or terminology aliases. Period strings alone do not
produce direct experience matches; no experience totals are calculated.

Facts retain original page/block and digital/OCR provenance and use stable IDs
within one request, such as `fact:0001`; these are not persistent candidate IDs.
Education and work facts also retain their original entry association through
bounded request-local `record_group` identifiers (`education:01`, `work:01`).
They follow original list positions, including empty entries; standalone skills
use null. These groups appear only in internal facts and semantic input, not
public evidence results, and introduce no persistent identity or database schema.
Skill criteria can use explicit skills, work roles and work activities. Education
uses qualification and field-of-study attributes; experience uses work roles,
periods and activities. Employer/institution identities, locations, education
dates and contact fields are omitted from the matching fact payload.

An exact value resolves as deterministic `supported`. If no facts in the relevant
categories were supplied, the result is deterministic `not_found`: this only
describes supplied evidence, not absence of a qualification. Otherwise it remains
unresolved for semantic interpretation. Empty skills can still use work evidence.

Groq receives only unresolved criterion IDs/categories/descriptions and relevant
fact IDs/record groups/kinds/values in explicitly marked untrusted JSON. The existing server-side
key/model configuration is reused. Strict structured output, temperature 0,
30-second timeout, 6000 completion-token limit and zero SDK retries are configured.
The serialized input is limited to 32,000 characters; over-limit requests fail
without truncation or an external call. One call per candidate may cover up to
50 criteria. There is no call if all criteria were deterministically resolved.

The model interprets evidence, not new facts. For example, Django REST-service
work can semantically support Python web development without asserting that
the CV explicitly lists Python. Degree equivalence, proficiency and experience
totals must not be invented; uncertain related evidence should be `ambiguous`.
Semantic correctness remains a model judgment requiring human review.

### Evidence validation and matching output

Provider output must contain exactly one result per unresolved criterion, with
no duplicate/unknown IDs or extra fields. Supported and ambiguous results require
1–8 unique evidence references; `not_found` must have none. Each reference must
identify an actual fact relevant to that criterion's category, and its copied
value must match that fact under the conservative normalization above. Returned
evidence values and source locators are copied from server-held facts, not model
metadata. Explanations are fixed server-controlled messages, avoiding unsupported
free-text provider claims.

The validator conservatively downgrades semantic `supported` education results
to `ambiguous` whenever cited evidence spans multiple education entries. This
prevents a bachelor's degree from one record being joined with Computer Science
from another to invent a linked degree. Same-entry degree/field evidence remains
valid even across different pages; sharing a page does not establish a shared
record. Already ambiguous results retain their status and evidence. Invalid
IDs/values still fail through the existing sanitized error contract.

This intentionally treats even legitimate broad multi-record education support
as ambiguous; it does not parse requirement wording with keyword heuristics.
Source-reference validation establishes provenance, **not guaranteed semantic
correctness**. Same-record or single-fact citations can still be insufficient
for a compound criterion. Work associations are supplied to the model, but no
new experience aggregation or work-record decision rule is implemented here.

`ScreeningMatchingResult` contains identifiers, parsing status, requirement
context, `matches`, `error_code` and an always-null `screening_decision`.
Each match has criterion ID, `supported` / `not_found` / `ambiguous`, method
`deterministic` / `semantic`, validated evidence and a concise explanation.

- `matching_complete`: exactly one match per criterion, in original input order.
- `source_unavailable`: parsing unavailable/failed; no matching nodes or provider
  calls run, and no criterion evidence conclusions are returned.
- `matching_failed`: no partial conclusions returned. Safe codes distinguish
  `semantic_not_configured`, `semantic_provider_failed`, `invalid_semantic_response`
  and `semantic_input_limit`. Timeout/provider failures never become `not_found`.

Hard/non-hard flags remain context only. Neither supported evidence nor completed
matching produces eligibility, exclusion, a suitability score or ranking.

### Privacy and boundaries

Contact identity is excluded because it is not a merit signal. Typed field
exclusion is not a semantic detector for personal information placed inside
free-text criteria or qualification values; trusted callers must keep these
inputs appropriate. **Unresolved job-related qualification values may be sent to
external Groq.** Use synthetic/sample data only for current verification; no
production consent/provider governance or authorization is implemented.

No raw qualifications, prompts, responses or secrets are logged by this increment.
Content is not persisted and does not enter candidate RAG. Prompts treat all input
as untrusted data; structured shape and allowlisted evidence reduce fabrication
risk but do not eliminate injection, prove real-world truth or guarantee semantic
relevance. Copying a valid fact ID alone cannot prove a semantic conclusion.
Bounded payloads can fail rather than support large profiles; no retry or lexical
fallback occurs. Candidate parsing/OCR behavior is unchanged.

## Planned — next WBS tasks

- **#647497:** evaluate verified hard requirements and implement the planned
  three-way outcomes. No such final decision is produced now; unavailable
  evidence must not be converted into automatic rejection.
- **#647498:** integrate the existing PostgreSQL checkpoint foundation with
  validated workflow/thread identity. This graph currently compiles with
  `checkpointer=False`; persistence and resumability are not claimed.

Authentication, approved-job persistence, API/UI integration and production
privacy controls remain separate work. Tests exercise the actual graph with
synthetic inputs and mocked Groq calls, including both source paths, preparation
compatibility, direct-match bypass, semantic evidence validation and failure states.
No live Groq call was performed for #647496; strict provider-schema acceptance
and real semantic quality are not established by mocked tests.
