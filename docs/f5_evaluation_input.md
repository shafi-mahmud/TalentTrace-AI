# F5: authorized finalized interview input

The later isolated Milestone 3 branch adds Q&A, mapping, a real LangGraph/Groq
assessment and recruiter UI. See [Milestone 3 interview analysis](milestone3_interview_analysis.md)
for implemented behavior and explicit synthetic-only/ephemeral limitations.
The following describes the original deterministic input increment.

## Evidence and requirements

Inspected on 16 October 2026. The local official source is
`Final_Project_doc_Business_Info_Document_AI_Recruitment_Platform_v2.pdf`
(Downloads; its cover states **Version 1.0, Issued for Execution**, despite the
filename). It is not copied into Git. Relevant references:

- Pages 13–14, F5: associate questions and answers, including follow-ups and
  multipart answers; assess relevance, factual/technical accuracy, completeness
  and articulation; map to requirements, justify with transcript references and
  identify unexplored requirements.
- Page 14 separates mandatory F6 consolidated assessment/report/component scores
  from F5; comprehensive interview scoring F9 is a stretch feature. No mandatory
  numeric F5 formula was found. Do not invent one.
- Page 21, sections 8.1–8.2: meaningful multi-step LangGraph evaluation orchestration
  is required, not a token one-node graph.
- Pages 18–19: capability separation, minimized synthetic data, no sensitive logs,
  external-service disclosure and deletion capability remain applicable.

No trainer-authored F5 clarification document was found in the inspected
repository or project-named local materials. Existing architecture PDFs are
**planned designs**, not trainer requirements: `TalentTrace_AI_LangGraph_Workflows_v1_1.pdf`
and `TalentTrace_AI_System_Design_v2_1.pdf` propose conditional Technical Reference
RAG, separate from Company Policy RAG, followed by evidence-backed evaluation and
human decision. A mandatory Technical Knowledge RAG requirement was not found in
the inspected BID. The current company-policy repository/embedding abstraction
is reusable design material, but its schema restricts collection to company
policy; it must not silently become a technical-reference knowledge base.

## Implemented first increment

Branch `feature/f5-evaluation-input`, based on F4 documentation commit `e36baf4`
and implementation `ca1f0af`. This branch depends on unmerged F4 and its single
migration chain through `0013_transcript_lifecycle`. No new migration or API was
added. The existing evaluation agent package was an empty placeholder.

Internal entry point:
`PostInterviewInputService(transcript_storage).prepare(request, job_id=..., interview_id=..., revision=...)`.

1. Authenticate the actual recruiter cookie; candidate access is refused.
2. Lock the owned interview row through the F4 persistence boundary. Check job
   association, durable revocation and retention; a missing retention deadline
   cannot authorize evaluation preparation.
3. Require current confirmed job criteria and exact interview/job/caller revision.
   Revision changes fail closed rather than silently evaluating against new rules.
4. Read bounded capture metadata and source turns under that same privacy lock.
   Refuse active/interrupted/failed/partial captures, missing or inconsistent
   completeness summaries, missing consents and unapproved consent versions.
5. Verify acknowledged and persisted turn counts, accepted/processed samples,
   unique event/sequence identities, role labels and timing within capture bounds.
   Both recruiter and candidate text must exist. Empty recognition is not evidence
   for a negative assessment.
6. Return a frozen structured envelope with job/interview/batch/upload/revision,
   retention deadline, confirmed criteria, capture references and finalized turns.
   It contains no email, credentials or CV details. Text is omitted from repr.

Bounds: 100 captures, 1,500 turns and 50 confirmed criteria. Exceeding a bound is
an explicit error, never a silently truncated evaluation input. Timing remains
relative to each capture, not a repaired global interview timeline. The envelope
does not invent Q&A pairs or infer who spoke inside a shared microphone.

`validate_quotes()` verifies nonempty, bounded exact quotations against known
turn UUIDs. Unsupported quotations and unknown references fail. This does not
decide factual accuracy, semantic contradiction, question pairing or skill level.
Conflicting transcript identity/completeness metadata is refused; semantic
contradictions remain future evidence-backed evaluation work.

## Privacy and completeness limitations

The envelope is **unverified ASR**, with `accepted_audio_only` completeness.
Completed capture processing does not prove a completed/full interview or perfect
recognition. The schedule has no authoritative actual-completion marker. Missing
evidence never means the candidate lacks a skill. Human review is still needed.

This service performs no database writes, model calls, evaluation or durable
payload caching. The interview-row-first lock serializes preparation with F4
writers/withdrawal. Committed withdrawal prevents subsequent preparation; text
already delivered to memory cannot be recalled. A returned envelope is **not** an
authorization token: future execution, retrieval and result persistence must
recheck current authorization/revocation/expiry/revision, with equivalent locking
at commit. No external evaluation is authorized by storage consent. Separate
clear disclosure and any necessary consent are required before provider use.

## Planned F5 execution

Reuse FastAPI authentication and F4 privacy services. The later explicit
LangGraph state/flow should be:

`authorized finalized input -> Q&A segmentation -> source validation -> job
requirement mapping -> conditional technical retrieval -> per-answer evaluation
-> source/output validation -> human-reviewable result`.

Keep original turn UUIDs, roles, capture-relative intervals and exact quotations
through every step. Follow-ups, multiple answers, ambiguous pairing, ASR errors
and unsupported claims must produce review-required states, not fabricated
evidence. Missing coverage is unexplored, not a hiring rejection. Use bounded
provider failure handling when implemented; no provider or retry runs now.
F6 consolidation, exports, comparison and any overall suitability presentation
are separate later increments. Do not create an unnecessary agent for this
deterministic input boundary.

## F4 browser status and activation

**Backend-only verified.** The preceding F4 verification exercised real local
tiny.en through authenticated ASGI/two WebSockets and disposable PostgreSQL;
speaker-attributed saving, residual drain, retrieval and withdrawal/deletion
passed. It did not exercise browser media or LiveKit.

This session found no listeners on demo frontend/backend 5184/8011, no installed
`livekit-server` command, and no cached LiveKit image (only PostgreSQL images).
The in-app browser showed sign-in service unavailable. No new cloud project,
microphone access, fake browser media or demo activation was substituted. A full
two-session browser/LiveKit/storage rehearsal remains blocked by that runtime
prerequisite and must not be reported as passed. Existing physical temporary
caption verification does not verify this storage UI.

Safe next rehearsal: provision a reviewed local LiveKit development runtime and
an isolated synthetic database through migration 0013; start one backend worker
and the feature frontend on unused loopback ports; keep email disabled and
cleanup enabled. Use two independently authenticated browser sessions and
approved synthetic audio injection. Verify temporary captions without storage,
both consents, saved review, and privacy withdrawal/deletion. No demo migration,
merge or production activation is performed by this increment.

## Validation

Synthetic unit/disposable PostgreSQL checks cover finalized input, missing or
contradictory metadata, incomplete captures, missing speakers, out-of-capture
timing, duplicate events, unsupported quotations, current revision, candidate and
foreign recruiter denial, withdrawn/expired/unestablished retention and no score
writes. The disposable fixture also checks Alembic upgrades/downgrades through
0013 and removes its own container. No Google, SMTP, cloud STT, LLM or real
candidate data is used. The final combined F5/transcript/consent/finalization/
caption/access/LiveKit regression run passed **164 tests**, including 29 F5 checks,
with the disposable PostgreSQL gate enabled. Python compilation and diff checks
passed. No frontend files changed; the preceding F4 verification recorded 177
frontend passes, TypeScript and production build success. This is not a new
browser verification claim.

Recommended next F5 increment: design and test evidence-linked Q&A segmentation
with offline fixtures, including follow-ups and ambiguous/multipart answers,
then introduce the multi-node LangGraph using the validated contract. Clarify
human review, actual interview-completion policy and external-AI disclosure before
live evaluation. Do not claim this input service is a functioning F5 evaluator.
