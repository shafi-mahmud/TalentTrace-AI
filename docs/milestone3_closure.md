# Milestone 3 closure — 16 October 2026

## Verdict

**PASS: controlled synthetic F4-to-F5 browser demonstration.** This supersedes
earlier PARTIAL rehearsal checkpoints. Broader BID/WBS acceptance remains partial:
this is not production approval, comprehensive competence assessment or a hiring
decision. F6 and Module 7 are not included.

Branch: `feature/milestone3-integration-hardening`. Implementation baseline:
`6bb1b6f`; this closure is a subsequent documentation-only commit.

## Verified execution evidence

| Boundary | Actual result |
| --- | --- |
| Browser media | Two LiveKit participants; generated synthetic speech only |
| Consent | Independent storage and temporary-caption consent |
| Recognition | Local CPU Faster-Whisper tiny.en, three actual timestamped turns |
| Finalization | Drained, saved, three acknowledged turns; accepted/processed samples matched |
| Source identity | Capture target, original turn IDs/text/roles and input fingerprint matched result |
| Q&A | One answered question; two candidate turns associated without rewriting |
| Requirement | Current confirmed revision 2; Python partial coverage |
| Retrieval | One versioned official-documentation summary, curated alias match |
| Inference | Groq / openai/gpt-oss-120b; completed operation, attempt 1 |
| Grounding | Exact transcript quotations, pair/role identities and reference citation revalidated |
| Browser result | Supported relevance, accuracy, articulation; partial completeness |
| Durability | Normal backend restart preserved attempt, timestamp and result hash; authorized GET 200 |
| Access | Anonymous and different-recruiter result reads denied |

The saved source is the actual browser-captured clear-speech interview, not a
seeded transcript. Recognition produced one recruiter turn and two candidate
turns. Synthetic saved eligibility used for disposable interview setup is a
fixture, not a new CV-screening claim. No transcript text was inserted or edited
to make this evaluation pass. No overall score or hire/reject decision exists.

One successful operation does not prove one provider call: the graph permits one
grounding-repair call, and successful per-call counts are not retained. Actual
inference is confirmed; exact one-versus-two calls is unknown. SDK retries are
disabled. No provider call occurred during closure verification or restart.
Graph execution is established by its implemented control flow and validated
persisted artifacts, not by a separately retained successful execution trace.

The reference `python313-lists-v1` is an attributed **curated paraphrase**, not a
verbatim crawl. Its source was checked during closure:
[Python 3.13 Tutorial, More on Lists](https://docs.python.org/3.13/tutorial/datastructures.html#more-on-lists).
The official documentation supports mutation and append behavior. The result
uses `official_documentation_summary`, not the `synthetic_demo` test corpus.
The corpus has five entries; local BGE semantic retrieval was not live verified.

## Failed cases and fixes

- Original four-turn fragmented capture: uncertain pairing; initial inference
  and repair failed grounding. Later retries exposed pairing-review and schema
  failures; old operation reached attempt 4. Full per-attempt history was not
  retained. A later deterministic needs_review/not_assessed result used no model.
- Worker import failure under root-launched backend: fixed cwd/model path in
  `f284ffe`; real worker WebSocket activation tests added in `10a7acf`.
- Empty failed capture blocked later saved capture: `75d48b1` omits only terminal
  interrupted/failed zero-turn history and discloses exclusion. Incomplete
  captures containing text remain blocked; historical rows remain unchanged.
- Rejected start stranded the UI operation ID: `ca2ff13` distinguishes definitive
  rejection from uncertain delivery; neither path automatically retries.
- `ddb2d6a` preserves safe grounding feedback; `8fee740` abstains on uncertain
  pairing; `f0328a5` tests review-result durability/deletion. `6bb1b6f` is test
  whitespace cleanup. No history was rewritten, pushed or merged.

Private verified PostgreSQL archives preserve failed captures/operations,
original review outcome, successful clear-speech source and completed evaluation.
No credentials, private links, operation identities or private records are
included in tracked documentation.

## Architecture decision: strict evidence and human review

**Implemented:** owned-interview authentication, durable privacy/retention and
revision checks precede LangGraph. The graph pairs source turns, maps criteria,
retrieves technical references, assesses confident pairs and validates exact
evidence. One repair is allowed. Uncertain pairs receive deterministic abstention.
Source/privacy are checked again before a fenced PostgreSQL result commit.
No transaction spans inference; result reads enforce the same privacy boundary.

**Decision:** do not rewrite ASR, weaken citations or treat missing evidence as
candidate rejection. Empty failed history is disclosed, not represented as speech.
**Tradeoff:** deterministic pairing/literal mapping are understandable but limited;
multipart answers, paraphrases and broad technical topics may require review.

## Final tests

- Backend: **141 passed, 0 failed, 0 skipped**, with disposable PostgreSQL and
  real local Whisper gates enabled: input, selection, Q&A, mapping, references,
  evaluation, API, durable recovery/privacy, captions and finalization.
- Frontend: **187 passed, 0 failed, 0 skipped**; TypeScript/build passed.
- Existing LiveKit bundle-size warning remains. Earlier broad-suite counts in
  historical notes are not a full-suite rerun on the final implementation.
- Closure adds documentation only; no new rehearsal, inference or demo migration.

## Remaining acceptance and privacy limitations

- Full BID/WBS sign-off is not claimed. README references docs/wbs.md, absent in
  this checkout. Scope follows the existing F5 documentation's BID review.
- Long natural interviews, multipart follow-ups, ASR accuracy, semantic coverage
  and broad corpus quality remain incompletely validated. This short answer does
  not establish comprehensive Python competence.
- Earlier physical F4 media/captions success is separate from this generated-
  speech F4-to-F5 run; they are not presented as one continuous session.
- Only synthetic external processing was authorized. No production or real-
  candidate activation. Storage and Groq disclosures remain separate.
- Withdrawal fences and verified deletion have disposable PostgreSQL tests; the
  successful source was not deleted for closure. Thirty-day retention tests do
  not prove thirty elapsed days. Offline private backups need separate access
  controls and timely disposal; application deletion does not erase archives.
- Pending signed consent receipts remain in process memory. Restart cannot
  reconstruct them; future captures need fresh independent acceptance.
- Completed result durability is verified. Exact provider-call counts, complete
  attempt history and successful node traces are not durably recorded.
- Disconnected UI may say storage disabled until both consent while a prior
  saved source/result remains authorized. Authoritative GET confirmed saved,
  unrevoked storage. This misleading live-form wording remains a known UI issue;
  no consent redesign was performed.
- F6 consolidated reporting/export/comparison and Module 7 remain unfinished
  outside this milestone scope. Demo databases and other worktrees are unchanged.

## Saved-result demo and viva

Use the private final-test login at local frontend 5190 while its isolated runtime
is available. Select Synthetic Python final speech verification and open its
existing interview. Load the saved three-turn transcript, distinguishing the
older empty failure. Check analysis status retrieves the existing result without
inference. If navigation lost the operation ID, use its private saved identity
with authenticated status GET; do not click Analyze merely to refresh a demo.
No media join, playback, new consent or retry is required for saved review.

Viva: LangGraph pairs actual speaker-labelled turns, maps confirmed requirements,
retrieves a versioned technical reference, asks Groq for advisory dimensions and
checks every quotation/citation. PostgreSQL saves only after source/privacy
checks pass. Restart retrieves the same result without inference. Missing evidence
remains a gap, not rejection; the recruiter makes the final decision.
