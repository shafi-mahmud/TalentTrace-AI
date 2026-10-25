# CV AI provider selection — 26 October 2026

CV AI starts unselected. Uploaded and previously imported batches use the same
compact selector, with the existing two allowlisted local Ollama models or configured
Groq. Local availability requires OLLAMA_ENABLED and installed model discovery at
the existing fixed loopback endpoint. No model is downloaded or activated here.

Both profile extraction and unresolved-requirement matching use the selected model.
The existing extractor/matcher prompts, strict schemas, textual grounding, evidence
references, deterministic scoring, job ownership, approved criteria and revision
checks remain in place. No browser-supplied CV text, endpoint or key is accepted.
Local failures never fall back to Groq. Small-model accuracy is unmeasured.

The profile and batch-screening APIs require X-TalentTrace-AI-Provider. Groq also
requires X-TalentTrace-External-Processing: confirmed. The unchecked UI disclosure
explicitly covers CV text and derived qualifications, and resets on provider,
job/revision or uploaded-batch changes. Older clients without selection fail closed.
This is recruiter authorization for transfer, not a claim of candidate consent or
legal compliance. Use only appropriately authorized records.

Successful score JSON includes separate _ai_provenance metadata: provider, actual
server-selected model and cloud-transfer confirmation. Existing score restoration
separates this metadata from the unchanged evidence/scoring contract; legacy records
still load. No migration is needed. An operationally incomplete batch returns its
failure states without replacing existing saved scores. Successful explicit reruns
retain the existing exact-batch/current-revision replacement policy.

Configuration remains server-owned; local credentials use a transport-only sentinel
which is never transmitted. Both local stages reuse the bounded no-fallback Ollama
adapter. Groq retains its existing bounded short-reset rate-limit behavior. No runtime
configuration or services were changed. Container loopback does not reach host
Ollama automatically; resource/network provisioning remains separate.

## Verification

Focused mocked backend tests cover both local model IDs and stages, strict output,
no fallback, consent/configuration rejection, ownership, legacy score restoration,
failed-run preservation and existing parsing/matching/auth contracts. Frontend tests
cover unselected defaults, CV-specific disclosure, exact headers and imported/uploaded
flows. No model inference, external provider request or browser acceptance was run.
Final test counts are recorded in the implementation commit's verification note.

Verification result: **173 backend passed, 1 PostgreSQL integration gate skipped**
(no disposable PostgreSQL target configured); **328 full frontend passed** before
final consent-reset adjustment, then **52 focused frontend passed** after it.
TypeScript and production build passed; existing >500 kB interview chunk warning
remains. No live model quality or browser layout acceptance is claimed.
