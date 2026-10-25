# JD Assistant local/API selection — 26 October 2026

Branch `feature/ai-provider-selection`, based on screen-sharing commit `17775d6`.
Scope is JD Assistant interpretation and grounded generation, not CV screening,
F4 STT, F5 evaluation or F11. No new framework, dependency, table or migration.

## User-visible behavior

JD AI is a compact selector starting with no choice. It lists configured Groq API
and two server-allowlisted local models: `qwen2.5:1.5b` and
`smollm2:360m-instruct-q4_K_M`. Unavailable options remain visibly disabled.
The Groq choice requires an unchecked-by-default explicit confirmation to send
JD conversation and policy context externally. New chat/restoration clears local
selection/confirmation. Publishing commands remain non-inference review actions.

Conversation state stores provider/local-model choice in its existing owned JSON
state. The existing job lock/ownership flow applies before interpretation. A
continuation using another choice is rejected; omitting selection cannot change
an established local conversation into Groq. Start a new chat to switch. Existing
Job Reference/revisions, copied evidence checks, policy retrieval, citation
validation and human review remain intact. Saved output identifies Ollama/Groq
and the actual server-selected model.

## Actual routing and configuration

- New setting `OLLAMA_ENABLED` defaults **false**. No runtime settings were changed.
  When enabled, authenticated capability discovery checks only fixed loopback
  `http://127.0.0.1:11434/api/tags` with a two-second timeout. Only the two IDs above
  can be advertised or selected, even if other models are installed.
- The local compatibility transport calls only `/api/chat` on that fixed endpoint,
  reusing existing interpretation/generation prompts and JSON schemas. Both stages
  run on the selected local model. Requests are non-streaming, bounded to 30 seconds,
  zero temperature, a finite context/output budget and `keep_alive:0`. Redirects,
  environment proxies, retries and cloud fallback are absent. Output size, selected
  model identity, completion, JSON and domain schema validation fail closed.
- The compatibility classes reuse Groq adapter validation, but their client factory
  is Ollama-only; an internal sentinel satisfies the existing constructor contract
  and is not an API credential or transmitted field. Result provenance is explicitly
  changed to Ollama before the normal workflow response validation.
- Groq uses its existing configured key/model, timeout/no-retry SDK and structured
  output adapter. Explicit selected requests require external confirmation. A key
  indicates **configured**, not verified free allowance or live service health.
- Browser requests accept only enum selection IDs and confirmation, not URLs,
  credentials, arbitrary models or tools. No credentials/endpoints are returned by
  capability discovery. Other recruiters cannot resume an owned conversation.

Compatibility: older requests without the new selection fields retain the existing
configured-Groq JD API behavior, subject to the conversation pin. The older direct
`job-descriptions/generate` endpoint is unchanged. This increment does not claim to
add transfer-consent enforcement to every historical API client. The new UI never
automatically selects/enables cloud, and local selection never falls back to it.

## Prerequisites and limits

Grounded JD generation still requires the existing configured policy document,
PostgreSQL and BGE embedding assets for either provider. Model availability is not
full JD-workflow readiness. For offline local use, provision those assets first and
use the existing HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE settings; this increment does
not change the shared embedding loader or download models. Nothing was installed,
loaded or downloaded during implementation.

An Ollama server on the host is not automatically reachable at container loopback.
No Docker networking change was made. Enable local inference only after a separate
resource/readiness review; RAM and swap on this laptop are constrained. Small
models may time out, fail strict schemas or request clarification. Their quality,
latency, policy compliance and technical reliability have **not** been measured or
claimed equivalent to a hosted model.

CV screening now has its own explicit selector and transfer-confirmation gate,
independent of JD selection. See [CV provider selection](cv_ai_provider_selection.md).
Selecting local JD alone still does not select or authorize CV processing.

## Verification

- Combined focused backend provider, recruiter chat/records, Groq generator and JD
  workflow tests: **153 passed, 0 failed/skipped** (31.22 s).
- Includes eight new mocked cases: local interpretation and generation, fixed URL/
  allowlist, explicit external confirmation, malformed/schema/wrong-model/timeout
  failures without fallback, authenticated discovery and cross-owner/provider-pin
  rejection. Ownership uses synthetic transactional SQL doubles, not a live database.
- Full frontend: **322 passed, 0 failed/skipped**. New tests check no default choice,
  unchecked cloud disclosure, strict capability IDs/no secret fields and explicit
  request selection. Existing refinement/publishing behavior is preserved.
- TypeScript and Vite production build passed; existing >500kB live-interview bundle
  warning remains. Whitespace checks passed. The initial new local-generator fixture
  used an invalid citation; using the existing valid policy fixture resolved it
  without relaxing production citation validation.

All model transports were mocked. No actual Ollama inference, Groq/paid request,
model download, provider activation, real candidate input, Docker operation,
merge or push occurred. Browser layout and real local/API quality acceptance are
outstanding. This is an implemented JD selection increment, not universal AI routing.
