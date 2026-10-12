# Multi-CV screening reliability — 12 October 2026

## Implemented diagnostics

Safe logs separate digital/source contract failures, Groq profile extraction,
structured-output validation, exact quote/value grounding, semantic provider calls,
semantic evidence validation, workflow status and score persistence. They retain
stage/category, candidate position, exception class, HTTP status, numeric token
usage and timings only. They never log original exception strings, source text,
quotes, names, prompts, provider output, credentials or bearer tokens.
INFO timings use `talenttrace.screening_diagnostics`; warnings expose safe failures.
Protected bodies/URLs must remain excluded from external logging too.

## Verified cause and bounded correction

Readable PDFs passed extraction in all 2/6/12 experiments. Back-to-back real calls
hit Groq HTTP 429. Safe metadata identified TPM and an 8,000-token/minute ceiling.
Each file can require profile extraction plus a semantic call. Observed short
profile calls used roughly 1,190 prompt tokens and 790–1,060 completion tokens;
matching added about 900 prompt tokens and 400–500 completion tokens. Larger
batches therefore exceed a minute's budget even when each document is short.
[Groq's header documentation](https://console.groq.com/docs/rate-limits) distinguishes
TPM token headers from daily request headers. These limits are shared with other
work using the account; an isolated database does not isolate provider quota.

The SDK still has `max_retries=0`. Only explicitly rejected 429s with a numeric
`Retry-After` of at most 59 seconds receive application recovery: at most two
retries, exponential minimum waits and a **60-second total wait budget per call**.
Daily quotas, missing/unsafe reset headers, exhausted retry budgets, timeouts,
400/422/authentication errors and validation failures are not retried. Original
model, strict schema, 6000 output cap, input bounds, graph and evidence rules remain.
No lexical/mock fallback, invented qualification or zero score for a failed file
is introduced. Failed files remain no-decision/not-evaluated; ambiguity can remain
eligible but unscored. Bounded recovery is not a guarantee of success.

One-retry trials recovered much of the batch but showed a second transient 429,
so the final policy permits two within the same total wait bound. They also found
an occasional evidence-validation rejection. Exact grounding remains unchanged;
safe `unknown_source`, `quote_not_in_source`, `value_not_in_quote` categories aid
diagnosis instead of relaxing validation or retrying until a fabricated fact passes.

## Experiment boundaries

Testing used a separate branch/worktree, a fresh localhost-only PostgreSQL/pgvector
database migrated through 0005 and backend port 8007. Synthetic digital PDFs used
three small templates repeated into 2/6/12-file batches, approved skill criteria,
100/0/0 weights and real Groq/LangGraph. Every response's scores were retrieved from
PostgreSQL and compared with the API result. This tests batch count, not long CVs,
scanned documents or all provider variability. No real candidate data or Discord
publication was used. The office and hands-on databases/services were not changed.

All experiments returned HTTP 200: HTTP success indicates a processed batch, not
that every candidate completed. Baseline eligible/scored counts were 2/2, 0/6,
0/12. Timeouts, 400/422 and structured-output failures were not observed in these
trials, so they are not claimed as the cause of the older demo failures.

Final policy comparison (real HTTP/provider calls; all digital extraction and
score retrieval checks passed):

| Files | Baseline parsed / matching complete / scored | Final parsed / matching complete / scored | Final request duration |
| --- | --- | --- | --- |
| 2 | 2 / 2 / 2 | 2 / 2 / 2 | 9.11 s |
| 6 | 2 / 0 / 0 | 6 / 6 / 6 | 81.87 s |
| 12 | 0 / 0 / 0 | 12 / 12 / 12 | 196.63 s |

Every final candidate was eligible, and stored score retrieval exactly matched the
API scoring response. This is a successful bounded experiment, not a guarantee
that every future CV should be eligible/scored. A separate one-retry trial produced
4 matching-complete candidates of 6 and 11 of 12; invalid evidence and ambiguity
correctly remained failures or unscored outcomes. No additional retry was applied
to those validation failures.

Automated backend suite: **1,073 passed, 6 skipped**. Initial full-run MCP tests
failed because the new worktree lacked its ignored MCP virtual environment;
supplying a read-only dependency junction fixed the environment and the final
suite passed. No publication or real provider requests occur in automated tests.
Frontend source/contracts were unchanged; frontend tests/build were not repeated.

## Remaining limits

Processing stays synchronous and sequential. Larger quota-constrained requests
can take minutes; backoff adds duration rather than hiding it. No whole-request
deadline/job queue was added. An ingress/browser timeout may leave the outcome
unknown: check persisted scores before repeating a batch. The browser has no
explicit fetch deadline; proxy/deployment limits still need verification.
Distributed quota coordination and large-document tests remain recommended.
Do not interpret absence of reproduced timeouts as ruling them out elsewhere.
