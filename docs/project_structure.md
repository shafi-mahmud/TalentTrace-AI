# Project Structure

## Implemented — current foundation

- `frontend/` is a React, Vite, and TypeScript application with a chat-first recruiter Job Description screen, inline generated drafts, policy citations, human-review notices and an explicit Discord publication action.
- `backend/` is a modular FastAPI application. It currently provides centralized settings, CORS configuration, automatic OpenAPI documentation, and `GET /api/v1/health`.
- `backend/app/db/` provides one shared SQLAlchemy `DeclarativeBase` and lazy factories for an async PostgreSQL engine and sessions. `DATABASE_URL` is optional during application import, is stored as a secret value when configured, and must use the `postgresql+asyncpg` scheme. SQL parameter values are hidden in engine diagnostics; importing the models or application does not connect to PostgreSQL.
- `backend/app/db/models/knowledge.py` implements the Database Design v1.3 `KnowledgeDocument` and `KnowledgeChunk` relationship as `knowledge_documents` and `knowledge_chunks`. Each document records one source version, collection (`knowledge_type`), title, and content hash; `source` is an opaque UUID, not a path. Each chunk retains its citation, index, hash, text, token count, heading paths, BGE model identity, and `Vector(384)` embedding. JSONB holds only heading-path metadata. A composite foreign key requires each chunk and its parent document to have the same collection. Unique constraints protect source versions, citations, and document/chunk indexes.
- `backend/app/repositories/company_policy.py` accepts validated company-policy source metadata, prepared chunks, and finite normalized 384-dimensional vectors. It verifies source/hash/citation/order consistency before opening a session, then stores the complete source version in one transaction. Duplicate versions are rejected without overwriting; failures roll back the whole batch. It does not chunk, embed, log policy content, or invoke an LLM. The JD workflow now uses its read-only exact cosine retrieval method; demo ingestion remains an explicit command.
- `CompanyPolicyRepository.find_nearest_chunks(document_id, query_vector, top_k=4)` implements exact pgvector cosine-distance retrieval for one explicit stored document/version. Both source and chunk queries filter `company_policy`; chunks also require `BAAI/bge-small-en-v1.5`. Query vectors reuse persistence validation, and `top_k` must be an integer from 1 to 5. Results are ordered by cosine distance ascending, then chunk index and citation ID. Invalid cosine distances are excluded. The method reconstructs immutable `RetrievedPolicyChunk` objects with validated source/citation/hash/heading metadata, without raw embeddings or arbitrary database metadata. Policy text remains untrusted reference data. Errors are controlled and do not echo policy text, vectors or database details. There are no approximate vector indexes; the repository does not perform request-to-embedding orchestration.
- **Implemented and verified — 06 Oct 2026:** exact cosine retrieval passed a live smoke test on disposable, localhost-only PostgreSQL 17.11 with pgvector 0.8.6. Three synthetic chunks with distinguishable vectors verified nearest-first ordering, bounded `top_k`, repeated tie ordering, source/citation metadata and embedding-free results. Another version of the same source remained isolated, and a Technical Reference document was rejected by the Company Policy query. The temporary container was removed afterward. The trainer-facing JD path now uses the semantic adapter described below.
- `backend/alembic/` contains a PostgreSQL-only migration environment and the first knowledge-table revision. It enables the `vector` extension before creating the tables, with no approximate vector indexes. Migration code, offline SQL, and live migration application are tested. From `backend/`, `python -m alembic upgrade head --sql` previews SQL without a database or credentials. Applying `python -m alembic upgrade head` to another environment requires a configured PostgreSQL service with pgvector installed and migration privileges. Application credentials should have narrower permissions than migration credentials. Downgrade drops the knowledge tables but retains the shared extension.
- **Implemented and verified — 06 Oct 2026:** the pgvector persistence foundation passed live validation using a disposable, localhost-only PostgreSQL 17.11 instance with pgvector 0.8.6. Validation confirmed actual `alembic upgrade head`, the enabled `vector` extension, `knowledge_documents` and `knowledge_chunks`, `Vector(384)`, a real synthetic repository write/read through a fresh session, duplicate rollback behavior, collection foreign-key enforcement, and downgrade/re-upgrade. The temporary test container was removed afterward. This verifies persistence, not a complete semantic RAG workflow or a production database deployment.
- `backend/app/services/recruiter_chat.py` maintains a bounded, short-lived multi-turn conversation and orchestrates JD creation; `integrations/llm/` and `integrations/job_publishing/` contain the implemented provider and MCP client boundaries. Other service/integration packages and business repositories remain planned.
- `backend/app/rag/` contains validated internal company-policy source and chunk contracts, deterministic heading-aware text chunking, and a deterministic lexical adapter retained only for reference and focused tests. The actual JD endpoint uses semantic BGE + pgvector retrieval, without lexical fallback.
- `load_demo_company_policy_source()` in `backend/app/rag/retrieval.py` loads the fixed synthetic demo file and validates its normalized contents. The lexical retriever and semantic demo seed share its existing source UUID, `synthetic-demo-v1` version and title; source/citation identity has not been renamed.
- `backend/app/rag/ingestion.py` implements reusable plain-text source orchestration: semantic BGE-tokenizer chunks -> ordered document embeddings -> one vector per chunk -> atomic `CompanyPolicyRepository.save_source_version()` -> stored document UUID. Chunking/tokenization and document encoding run through `asyncio.to_thread` with the same embedding service. Existing layers retain validation ownership. Failures identify the stage without exposing policy text, vectors, paths or database details. Duplicate source/chunk conflicts are rejected without replacing existing data.
- `backend/app/rag/seed_demo_policy.py` provides an explicit synthetic demo seed command. From `backend/` with its virtual environment active, run `python -m app.rag.seed_demo_policy` after configuring `DATABASE_URL` and applying the Alembic migration. It uses centralized settings and the existing engine/session factories, repository, BGE adapter and fixed demo source. Output is limited to success plus document UUID, or a controlled failure; model-library diagnostics are suppressed. Duplicate seeds fail with a nonzero exit and an existing-source/chunk-conflict message. Nothing is seeded, loaded or connected during normal application import/startup, and `.env` is not modified. This is demo seeding, not an upload endpoint, arbitrary filesystem ingestion or production policy management.
- **Implemented and verified — 06 Oct 2026:** the actual seed command passed with the existing synthetic demo file, cached/local BGE model, real migration and disposable localhost-only PostgreSQL 17.11/pgvector 0.8.6. It stored three semantic chunks with normalized 384-dimensional document embeddings and matching source/version/content citation identities, printing only success and its document UUID. The standalone semantic retriever used that UUID and ranked Remote and Hybrid Work Wording first for a synthetic remote-engineering request, returning citations without embeddings. Rerunning the command rejected the duplicate without changing document/chunk counts. The temporary container was removed afterward; its document UUID does not refer to a persistent deployment. The returned UUID must be explicitly configured for the semantic JD workflow; no latest/active policy is selected automatically.
- `backend/app/rag/embeddings.py` provides a replaceable embedding protocol, a lazy local `BAAI/bge-small-en-v1.5` adapter, and a BGE tokenizer counter. It returns validated, normalized 384-dimensional vectors, prefixes retrieval queries only, and rejects text exceeding the model's 512-token limit instead of truncating it. Model loading happens only on explicit embedding or token-counting calls; importing the application does not load or download the model. The counter can share the encoder's model/tokenizer and excludes special tokens from chunk counts. The semantic JD retriever now uses this layer for query embeddings; the reference lexical adapter does not.
- `backend/app/rag/semantic_retrieval.py` implements the `SemanticCompanyPolicyRetriever` used by the JD workflow through the existing retriever interface. It converts validated job requirements into a deterministic, fixed-order query with explicit labels for title, summary, responsibilities, skills and supplied optional fields. It calls the injected local `EmbeddingService.embed_query()` using `asyncio.to_thread`, then delegates to the repository's exact cosine query for one configured document UUID and `top_k` (default 4, bounded 1–5). The embedding service adds the BGE instruction; the adapter does not add it again. Results pass through as the existing immutable `RetrievedPolicyChunk` tuple. Construction/import does not load a model or create/connect a database engine. Query-construction, embedding and unexpected retrieval failures are sanitized; existing controlled repository errors are preserved. No request, policy content or vectors are logged.
- Semantic query text is not summarized, clipped or silently truncated. This simple strategy preserves the supplied requirements, but a valid long JD request may exceed BGE's 512-token budget. The embedding service checks the complete input, including its instruction and special tokens, and the adapter returns a controlled retrieval error before encoding or database search when that limit is exceeded.
- **Implemented and verified — 06 Oct 2026:** standalone request-to-BGE-to-pgvector semantic retrieval passed with the cached/local BGE model and a disposable, localhost-only PostgreSQL 17.11/pgvector 0.8.6 instance. Three synthetic policy sections used real tokenizer-aware chunks and normalized 384-dimensional document embeddings. A synthetic privacy-engineering request used real BGE query encoding and ranked Privacy and Data Protection first. Validation confirmed the configured two-result limit, source/citation metadata, explicit document/version scoping and no returned embeddings. The temporary container was removed afterward. The subsequent end-to-end validation below confirms its integration with JD LangGraph, API and semantic response metadata.
- `chunk_company_policy_for_semantic_retrieval()` in `backend/app/rag/chunking.py` prepares deterministic, citation-bearing company-policy chunks using BGE tokenizer counts: at most 400 tokens including headings, with up to 50 tokens of overlap at word boundaries and no tokenizer truncation. It reuses the existing chunking algorithm and uses only the embedding service's tokenizer, without generating vectors. The generic default remains 700/75; the lexical demo continues to explicitly use 500/50 with whitespace counting. This preparation helper is not semantic retrieval and is not wired into the JD workflow.
- `backend/app/agents/jd/` contains the bounded three-node LangGraph: `retrieve_policy_context` -> `generate_draft` -> `validate_draft`. Its lazy factory creates the async engine/session factory, company-policy repository, local BGE service and semantic retriever for the explicitly configured `COMPANY_POLICY_DOCUMENT_ID`, then the existing Groq adapter. Retrieval embeds validated recruiter requirements and performs exact pgvector cosine search before generation. Citation validation allows only retrieved context IDs. The result is an unapproved draft requiring human review; drafts are not persisted or approved.
- `backend/app/integrations/llm/` contains the Groq structured-output adapter used by the Job Description workflow. The API key remains optional during application startup and is required only when generation is invoked.

- **Implemented and verified — 06 Oct 2026:** the real FastAPI JD endpoint passed end-to-end validation through the three-node LangGraph, local BGE query embedding, exact pgvector cosine retrieval and Groq strict structured output (`openai/gpt-oss-120b`). Actual Alembic migration and the explicit demo seed command ran against disposable localhost-only PostgreSQL 17.11/pgvector 0.8.6. The response was HTTP 200, `draft`, `human_review_required=true`, `retrieval_mode=semantic_bge_pgvector`, with meaningful JD sections and three citations belonging to the seeded synthetic policy source. No raw policy document, embeddings, credentials or database configuration were returned. An unknown configured document UUID returned the sanitized HTTP 502 failure, without lexical fallback. The temporary container and data were removed afterward; this was validation, not production deployment.
- Retrieval modes are bounded internal contracts reported by the retriever and copied into the strict public response. The reference lexical adapter reports `deterministic_lexical_demo`; the main endpoint exclusively uses `semantic_bge_pgvector`. Frontend response validation requires the semantic mode and displays Semantic BGE + pgvector, while retaining the synthetic demo-source disclosure. The source panel describes the server-side demo architecture; it is not a live source-readiness check.
- `COMPANY_POLICY_DOCUMENT_ID` is an optional validated UUID at startup, identifying the stored document returned by the explicit seed command. JD generation requires it and `DATABASE_URL`; missing configuration returns the generic HTTP 503 response. Retrieval failures return the generic HTTP 502 response, and provider timeouts retain HTTP 504. Import/startup does not connect to PostgreSQL, load BGE, seed policy or call Groq. There is no lexical fallback for configuration, model, database or document failures.

## Required synthetic semantic demo setup

1. Make PostgreSQL with pgvector available and set a local `DATABASE_URL` using `postgresql+asyncpg`. Keep real credentials in ignored local configuration; grant migrations appropriate privileges.
2. From `backend/` with its virtual environment active, run `python -m alembic upgrade head`.
3. Make the local `BAAI/bge-small-en-v1.5` model available and run `python -m app.rag.seed_demo_policy`. This explicitly seeds only the repository's synthetic policy. Repeating the same source/version is rejected; it does not replace existing data.
4. Set server-side `COMPANY_POLICY_DOCUMENT_ID` to the UUID printed by that seed command, in local `.env` or process environment. Do not use a UUID from a removed disposable smoke database. Restart the backend after changing configuration; the workflow factory is cached per process.
5. Set local `GROQ_API_KEY` and `LLM_MODEL=openai/gpt-oss-120b`. Recruiters cannot choose document IDs, credentials, models or provider settings through the request.
6. From `backend/`, run `python -m uvicorn app.main:app --reload`. From `frontend/`, run `pnpm dev` and open its displayed local URL. The existing Vite proxy forwards API requests to the backend. Generate a synthetic JD and review the draft and policy citations.

**Limitations:** exact search is bounded to one explicit company-policy document (default top-k 4), without approximate indexing or a relevance threshold. Full labeled requests exceeding BGE's 512-token limit fail safely rather than being truncated. Citations prove traceability to retrieved context, not that every generated claim is correct. Automated frontend response tests and the production build passed; manual browser/visual validation was not performed in this increment.

## Implemented — local external policy preload

Local operator-driven PDF/DOCX/TXT/Markdown policy preload is now implemented
through `backend/app/rag/policy_files.py` and the explicit
`python -m app.rag.ingest_policy_file` CLI. It reuses the existing validated
source, BGE-small chunking/embeddings and repository pipeline, without a schema
migration, JD graph change or automatic policy selection. See
[local Company Policy ingestion](company_policy_ingestion.md) for limits,
safe commands, source/version/document UUID semantics and the documented
decision to preserve BGE-small while deferring model benchmarks.

## Implemented — PostgreSQL checkpoint foundation

- `backend/app/db/checkpointer.py` provides the official LangGraph
  `AsyncPostgresSaver` lifecycle with strict serialization. A separate checkpoint
  database on the same PostgreSQL instance keeps LangGraph-owned tables apart
  from application tables and Alembic. Setup is explicit through
  `python -m app.db.setup_checkpointer`; import/startup remains lazy.
- `backend/app/db/workflow_threads.py` validates opaque UUID-based identifiers
  in the four workflow namespaces, without implementing those workflows.
- See [checkpoint storage](checkpoint_storage.md) for configuration, setup,
  ownership, Windows async compatibility and the two-process validation helper.
  This establishes infrastructure only; it does not checkpoint the JD workflow.
- **Implemented and verified — 07 Oct 2026:** live setup in a separate database
  on the preserved PostgreSQL instance and a genuine two-process interrupt/resume
  proof passed. Business/RAG tables and data fingerprints remained unchanged.
  All 35 focused tests and 50 backend tests passed on the standalone
  infrastructure branch before this integration.

**Implemented and verified:** the checkpoint foundation. **Planned:** wiring
the existing JD workflow into that foundation; the JD workflow is not yet
checkpointed, and JD approval/revision is not implemented.

## Implemented — recruiter chatbot JD creation slice

- `POST /api/v1/recruiter-chat` accepts a bounded, plain-text recruiter message
  through `schemas/recruiter_chat.py`. The replaceable interpreter in
  `integrations/llm/recruiter_chat.py` uses the existing Groq configuration and
  official async client with strict structured output to extract requirements;
  it never generates the final JD or receives company policy or server secrets
  in its prompt. Provider calls use an explicit timeout and no automatic retries.
- `services/recruiter_chat.py` validates copied source evidence for each extracted
  value after Unicode/whitespace normalization. It allows narrow enum mappings
  and terminal punctuation/finite leading-verb normalization, while preserving source-backed role
  purpose rather than inventing polished prose. Negated/ambiguous clauses,
  unsupported list items and years without explicit experience context trigger
  clarification before generation; invalid items are never silently filtered.
  It applies the existing `JobDescriptionGenerationRequest` validation. Only a
  complete valid request invokes the existing `get_job_description_workflow()`.
  Its semantic Company Policy retrieval, generation and citation validation are
  reused unchanged. The chatbot is an interface/orchestrator, not a fifth graph.
- The React recruiter screen is chat-first: distinct messages appear in a scrollable
  conversation with the composer anchored below it and a demo-load button.
  Generated JD sections, draft/human-review notices and grouped policy grounding
  appear inline in the assistant message; technical citation IDs remain collapsible.
  Clarification stays in the conversation. The manual structured form and separate
  result panel are not part of this screen; the structured JD API remains unchanged.
  Generation remains an unapproved draft; errors use fixed public messages.
- **Implemented — demo publication:** `POST /api/v1/recruiter-chat/publish` accepts
  a strict, bounded publication DTO matching the standalone `JobCircular` limits.
  `integrations/job_publishing/mcp_client.py` uses official MCP SDK v2.3.0 and stdio
  to launch the existing server with its separate virtual environment. It calls
  `publish_job` once; only that server contacts Discord. It returns validated
  destination/status/external-ID metadata and hides raw tool/subprocess errors.
  The server reads ignored local configuration; webhook credentials never reach
  the browser. Optional source-validated location/employment/work arrangement
  are returned as `publishing_context`, with `on_site` mapped to MCP `onsite`.
  Oversized content is rejected, never truncated. Applying a timeout can leave
  delivery unconfirmed; there is no automatic retry.
- Each inline draft has Publish to Discord and Revise draft actions. Publication
  requires an explicit review/demo confirmation, shows loading/success/failure,
  and locks that card after one attempt. Revision loads the last recruiter message
  into the composer. Citations remain accessible in a compact collapsible section. Text posting instructions direct
  recruiters to the reviewed draft action instead of automatically publishing.
- **Limitations:** formal publication approval, audit and server deduplication
  are not implemented. Publication now requires an authenticated recruiter-owned saved
  draft whose generated content matches the server record. Page reload/new requests can publish again. Check Discord
  before another attempt after an unconfirmed result. Automated SDK/server
  protocol tests replace Discord. On 07 Oct 2026, the project owner confirmed
  live UI-to-FastAPI-to-MCP-to-Discord publication.
- Recruiter conversations are now owner-scoped PostgreSQL records, with a
  30-minute idle lifetime, 20-turn and 12,000-character limits. The browser sends
  only an opaque conversation UUID; server-side validated state is restored per
  request under a row lock. Successful turns and generated drafts are committed
  together. Unchanged complete requirements do not repeat JD generation.
  Saved history remains readable after conversation expiry, but new turns require
  a fresh conversation. See [Recruiter job ownership](recruiter_job_ownership.md)
  for deployment prerequisites and validation limits.
  Bounded input accepts multiline text, tabs,
  comparisons and job descriptions involving resume/transcript processing.
  React renders messages as escaped text. Input rejects unsafe control characters,
  unknown request fields and obvious emails, phone-like contacts, named candidate/
  applicant patterns and CV/resume submission/possessive patterns. These heuristics
  are not comprehensive personal-data detection; enter only job requirements.
  Evidence checks are not full semantic verification. Conservative clause negation
  may ask for clarification on legitimate mixed-polarity wording; copied phrases
  cannot prove every requirement is correctly classified or fully extracted.
  Human review remains required.
- Automated tests mock Groq and retrieval/generation boundaries; an API test runs
  the existing JD graph with those boundaries replaced. The chat interpreter/provider
  schema and full grounded JD API path passed live verification on 07 Oct 2026. The project owner confirmed manual chat-first UI verification. Existing
  BGE query-length limits still apply to extracted requirements.
- **Planned:** formal JD approval/revision, publication audit/deduplication and
  production access/retention governance. Recruiter authentication, job ownership
  and stored conversation history are implemented in code; live deployment of
  the new migration and account provisioning remain unverified in this increment.
  The JD LangGraph remains unchanged.

### Implemented — shared saved-job screening requirements

- Generated JDs automatically select one owned saved job in both workspaces;
  there is no transfer/setup button inside the JD card. Candidate Screening is the
  single place to edit and confirm requirements. Manual job creation remains
  available without JD generation. References are generated from persistent job
  UUIDs, not typed by the recruiter or invented by the LLM.
- Recruiter-grounded suggestions start preferred. Two curated, concrete synthetic
  demo-policy practices may also be suggested for security/privacy-related roles:
  access controls and incident reporting. The mapping pins the approved source
  UUID, version and normalized content hash, requires retrieved source excerpts,
  and retains citations. General policy prose is not automatically converted into
  hiring criteria. Policy suggestions remain preferred until explicitly changed
  and confirmed by the recruiter; this is not a policy-ingestion/rule engine.
- Criteria confirmation saves an exact PostgreSQL snapshot with an optimistic job
  revision check. Editing clears local confirmation/results; confirming saves the
  new snapshot. Server-side screening rejects any snapshot differing from the
  saved approved criteria. Draft regeneration clears saved approval. Saved jobs
  and history can be reloaded; result and uploaded-batch selection remain in React
  memory. Switching jobs keeps uploaded files but prevents mismatched screening.

## Implemented — standalone MCP job-publishing foundation

- `job-publishing-mcp/` contains a TalentTrace-owned official Python MCP SDK v2
  stdio server with one `publish_job` tool, a strict `JobCircular` contract and
  an async Discord webhook adapter. Credentials stay server-side; mentions are
  disabled, oversized payloads are rejected and provider failures are sanitized.
- Mocked tests verify the adapter and MCP protocol. **Implemented and live
  verified — 07 Oct 2026:** MCP-to-Discord publication used synthetic job data,
  returned confirmed external publication metadata and visibly appeared in the
  `#job-openings` demo channel. The bounded backend MCP client and inline Discord action are now implemented
  as described above. JD approval enforcement and other destinations remain planned;
  the JD workflow remains unchanged. See [job-publishing MCP](../job-publishing-mcp/README.md).

## Implemented - optional external application link and CV collection demo

- Backend `APPLICATION_FORM_URL` is optional, validated HTTPS configuration kept
  in environment/ignored root `.env` and protected as a secret setting. Only the
  backend adds it to the MCP `JobCircular.application_url`; recruiter requests,
  generated JD fields and LLM output cannot override it. No URL is returned in
  the destination/status/external_id response or sent to the JD Agent.
- Each demo publication gets a backend-derived `TT-JOB-<16 uppercase hash characters>`
  reference from normalized publication content. The required MCP `job_reference`
  is bounded to 40 safe uppercase/digit/hyphen characters. Discord displays
  **Job Reference** immediately before **Apply for this role**; candidates copy it
  into the external form. HTTP recruiter requests and LLM output cannot supply it.
  The authenticated backend now supplies its stable saved-job UUID-derived
  reference; standalone MCP clients remain responsible for their own references.
  This is not publication deduplication. Automatic form
  prefilling remain planned.
- The standalone MCP contract accepts the optional link, and the Discord adapter
  includes **Apply for this role** while enforcing existing embed limits and
  disabled mentions. Missing configuration preserves publication without a link.
- **Implemented external CV collection demo path, once configured:** Discord ->
  application link -> manually created Google Form -> form owner's Google Drive.
  Link mapping/validation/presentation are mocked-tested. On 07 Oct 2026, the
  project owner confirmed live Discord-to-Form-to-Sheets/Drive CV collection.
  Google Form/Drive is an external privacy
  dependency, not native TalentTrace storage. See [CV collection demo](cv_collection_demo.md)
  for setup, Google sign-in requirements and a single synthetic manual demo.
- **Planned:** native candidate portal, Drive API synchronization, automatic CV
  import, candidate persistence, weighted scoring, candidate
  authentication and retention/deletion automation. Production approval/audit
  and additional publishing destinations remain planned. No CV data is sent
  through the JD workflow or MCP publishing by this link feature.

## Implemented - native batch CV intake and Candidate Screening foundation

- **Candidate Screening** is a separate top-level frontend mode; JD Assistant
  remains the default chat-first experience. Screening works without generating
  a JD: recruiters can create an owned job title and enter requirements
  directly, then explicitly review and confirm mandatory/preferred flags using
  the same `ReviewedJobSnapshot` contract. Manually entered criteria are not
  presented as policy-backed. JD-generated criteria remain isolated by draft ID.
- Criteria setup and CV batch upload can happen in either order. Changing the
  Job Reference invalidates criteria confirmation and screening results while
  preserving the already uploaded batch, so recruiters can finish setup without
  re-uploading it. Confirmed criteria are now stored against an owned job profile.
- Recruiters select 1-20 PDF/DOCX files, remove selections and see controlled
  upload status.
- `POST /api/v1/cv-uploads` accepts bounded multipart UploadFile parts, validates
  reference syntax, extension/MIME, PDF signatures and DOCX ZIP structure, then
  streams files to private ignored local storage. Responses contain UUID batch/
  upload IDs and sizes only. A failed batch cleans up its own stored files.
- `CV_UPLOAD_ROOT` defaults to ignored `data/cv_uploads/`; no files are web-served.
  No candidate data is logged, sent to JD/RAG/MCP or stored in candidate tables.
  Intake now requires recruiter authentication and uses owner-specific storage.
  It still lacks production
  retention/deletion controls. Job association is checked against the owned saved
  record; file manifests are not candidate/application database records.
- The external Google Form/Drive demo remains separate and already verified.
  Automatic Drive import, weighted scoring,
  candidate persistence and Docker volume integration remain **Planned**.
  See [native CV ingestion](cv_ingestion.md) for limits, storage and security caveats.

## Implemented - primary CV digital-text extraction (#647488)

- **Extract text** in Candidate Screening processes a stored batch through
  `POST /api/v1/cv-uploads/{job_reference}/{batch_id}/extract`. A synchronous
  service runs in the threadpool and preserves all originals.
- PyMuPDF extracts PDF text with 1-based page evidence. python-docx preserves
  paragraph/table interleaving with ordered body-text blocks. Internal immutable
  evidence is held only in memory; public responses and frontend state contain
  metadata only, never extracted CV text or private paths.
- PDFs need at least 80 alphanumeric characters overall and at least 50% of pages
  with 20 alphanumeric characters each to pass the explicit digital-text heuristic.
  Otherwise **OCR required** is shown; a separate fallback action is described
  below. Insufficient text is not evidence of missing qualifications. DOCX does
  not route to OCR.
- Per-file parser failures are sanitized; other files remain independently
  processable. Storage validation and document/text limits are enforced. See
  [CV ingestion](cv_ingestion.md) for exact limits and heuristic limitations.
- Candidate persistence, screening/scoring, background processing, automatic Drive import, production authorization governance
  and production retention/deletion remain **Planned**. This is not a new agent or
  LangGraph workflow and does not send CVs to JD/RAG/MCP.

## Implemented - CV OCR fallback (#647491)

- **Run OCR** calls `POST /api/v1/cv-uploads/{job_reference}/{batch_id}/ocr`.
  It reuses safe private lookup and primary extraction. Only `ocr_required` PDFs
  qualify; digital PDFs, failed PDFs and DOCX bypass OCR. No eligible PDFs is a
  successful no-op without installation checks.
- PyMuPDF integrated Tesseract performs English full-page OCR at 300 DPI on
  low-text pages, preserving meaningful digital pages where possible. Immutable
  internal evidence records page number and `digital`/`ocr` source. Output is
  extraction evidence, not verified candidate truth.
- Public API/UI show metadata only. No raw OCR text, file/tessdata paths, original
  filenames, sidecars or candidate records are returned/persisted. Originals stay
  unchanged. OCR failures are per-file; missing English data is sanitized 503
  `ocr_not_configured`. A shared PDF lock serializes native work in the threadpool.
- Limits: 25 pages/document, 100 eligible PDF pages/batch, 25 million rendered
  pixels/page and 500,000 output characters/document. See [CV ingestion](cv_ingestion.md)
  for exact routing, success checks, setup and limitations.
- **System dependency:** Tesseract English language data; optional lazy
  `OCR_TESSDATA_PATH`, otherwise local discovery. No new Python dependencies.
  **Real local OCR was manually verified by the project owner on 07 Oct 2026**:
  synthetic image-only PDF -> `ocr_required` -> Tesseract 5.4.0.20240606 ->
  `ocr_extracted`; 31 focused OCR tests were reported passed. The earlier dependency
  blocker was resolved; English data/version were detected in the profile increment.
- Candidate persistence, screening/scoring, automatic Drive
  import, background processing and production retention/deletion
  remain **Planned**. No new workflow/agent was added.

## Implemented - source-backed candidate profile extraction (#647493)

- `schemas/candidate_profile.py` separates private source/evidence/provider contracts
  from public profiles, and contact identity from qualifications. Every public fact
  has a server-derived page/block and digital/OCR locator; full text/quotes stay private.
- `services/candidate_profile.py` reuses stored-batch validation, primary extraction
  and OCR fallback, then validates every returned fact. Unknown sources, absent
  quotations and invented/inferred values fail the whole file. Skills are deduplicated
  in source order. Failed source extraction is `source_unavailable`, not missing skills.
- `integrations/llm/candidate_profile.py` provides the replaceable extractor interface
  and Groq strict JSON implementation: existing key/model, 30-second timeout, zero
  retries, temperature 0 and one sequential call per usable CV. Input limits are
  40,000 characters and 400 units; no silent truncation. This is not a new workflow.
- `POST /api/v1/cv-uploads/{job_reference}/{batch_id}/candidate-profiles` accepts
  stored identity only. Missing provider setup is sanitized 503; individual provider/
  grounding failures are `parsing_failed`. Other files continue; originals stay unchanged.
- Candidate Screening uses `api/candidateProfiles.ts`, `types/candidateProfile.ts` and
  `components/candidateProfilesPresentation.ts` for an Extract candidate profiles
  action and compact Contact/Education/Work history/Skills results. Focused backend
  and lightweight frontend tests cover contracts, grounding, source routing and safe UI.
- **Privacy:** this feature sends CV-derived text to external Groq. Synthetic/sample
  data only; recruiter authentication exists, but production provider governance does not. Text/evidence
  is not persisted; profiles stay in request/component memory. CVs do not enter JD,
  RAG or MCP. Repeated processing may repeat extraction/OCR/provider calls.
- Grounding confirms textual support, not verified candidate truth. Candidate
  persistence, weighted scoring, background workers and production consent/retention remain
  **Planned**. Future merit evaluation must exclude contact identity.

## Implemented — Screening preparation, hybrid matching and decisions (#647495–#647497)

- `backend/app/schemas/screening.py` validates explicit bounded criteria and
  qualifications-only inputs using existing candidate source-status semantics
  and the syntactic demo Job Reference. It accepts no contact or raw CV fields.
- `backend/app/agents/screening/workflow.py` implements input validation,
  requirement grouping, source-readiness checking and conditional result nodes.
  `prepare()` preserves `ready_for_matching` or `source_unavailable` results.
  `match()` extends the same graph with conservative whole-value deterministic
  matching, one Groq call for unresolved criteria when needed, evidence-reference
  validation and ordered requirement-level results. Provider inputs contain only
  unresolved requirements and relevant qualification facts, without contact fields.
- Matching returns `supported`, `not_found` or `ambiguous` evidence statuses,
  not verdicts. Operational failure returns `matching_failed` with a safe code
  and no partial conclusions. Parsing failure bypasses matching; empty skills
  alone do not cause exclusion during matching. `prepare()` and `match()` retain
  null screening decisions.
- `screen()` reuses matching and adds deterministic hard-requirement evaluation
  with conditional eligible/excluded/insufficient-evidence result nodes. Any
  completed hard `not_found` excludes; otherwise hard ambiguity yields insufficient
  evidence; otherwise the candidate is eligible for later scoring. Non-hard
  criteria do not independently exclude. Source/provider failures bypass decisions.
  Results preserve matching provenance and list all unmet hard IDs with structured
  "not demonstrated in the parsed CV" reasons; no negative evidence is fabricated.
  Incomplete CVs or extraction/matching errors can cause false exclusions.
- **Privacy:** semantic matching can transmit CV-derived qualification values to
  Groq. Inputs/outputs are bounded, evidence IDs/values are allowlisted and
  source locators are server-derived; validation does not prove semantic truth.
  Only synthetic/sample data is appropriate for the current demo.
- **Implemented — #647498:** trusted internal PostgreSQL checkpoint start/resume
  for the same Screening graph, with opaque thread identity, exact request
  snapshot guards and strict JSON-safe state boundaries. Default methods remain
  non-persistent. Actual-graph unit tests verify resumed evaluation without
  repeating completed matching. **Unverified:** live Screening PostgreSQL
  cross-process recovery (local checkpoint configuration missing; Docker
  unavailable on 08 Oct 2026). The opt-in proof uses synthetic data and mocked
  semantic calls; the earlier checkpoint foundation proof is separate.
- Weighted scoring, business candidate persistence, API/frontend checkpoint
  integration and production access/retention controls remain **Planned**.
  See [Candidate Screening](candidate_screening.md) for graph flow, limits and
  failure behavior. This increment made no live Groq calls.

## Implemented — reviewed criteria and native CV batch screening

- Shared saved-job criteria review is described above. All suggestions start
  preferred; explicit confirmation is criteria approval, not a hiring decision or
  formal publication approval. The stored snapshot is job- and owner-bound.
- `POST /api/v1/cv-uploads/{job_reference}/{batch_id}/screen` requires authentication
  and an exact saved approved snapshot. Files are resolved from that recruiter's
  private upload root. Existing parsing/OCR and `CandidateScreeningWorkflow.screen()`
  are reused. No contact fields enter evaluation; provider/source failures remain
  distinct from exclusion. Existing evidence, hard decisions and ranking are unchanged.
- CV upload, extraction, OCR and profile routes also require job ownership.
  Historical uploads in the old shared root are not automatically adopted by an
  account. Results and selected batch identities remain browser-memory state;
  candidate/application persistence and automatic Drive import remain planned.
- Automated business-contract tests use explicit authentication doubles. Separate
  ownership tests exercise real authentication/authorization with a transactional
  database double. Separately, on 09 Oct 2026 isolated real PostgreSQL migrations,
  account provisioning, HTTP ownership/persistence and authenticated browser shared-job
  checks passed. Provider and embedding outputs were synthetic fixtures; no live
  Groq or Discord call was made. See the ownership document for exact boundaries.

## Implemented — Milestone 1 requirement-based candidate ranking

- `services/screening_ranking.py` ranks only completed `eligible` decisions in one
  confirmed job-reference/batch snapshot. It counts `supported` requirements,
  treating validated deterministic and semantic support equally. Mandatory flags
  still control eligibility through the unchanged Screening graph; preferred
  ambiguity does not add support. Zero-support eligible candidates remain ranked.
- The batch response includes validated ranking entries: upload ID, rank, tie flag,
  supported/ambiguous/not-found counts and total requirements. Descending support
  uses competition ranks (`1, 1, 3`); upload UUID orders tied display only. Neither
  contact attributes nor a new provider call participates in ranking.
- The CV workspace displays eligible ranking with expandable unchanged evidence
  and digital/OCR provenance. Exclusions, insufficient evidence, unavailable sources
  and processing failures remain visible in separate unranked sections.
- **Classification gap:** `supported`, `ambiguous` and `not_found` are evidence
  statuses, not an automatic Met / Partially Met / Unmet classification. Ambiguity
  means uncertainty and does not establish partial fulfilment. A future partial-match
  policy would require explicit reviewed subcriteria and validation; none is inferred.
- No weighted 0–100 suitability score, cross-job/batch ranking, durable job-profile
  scoring system or extra graph/agent is added. Criteria snapshots now persist;
  ranking results remain browser-memory only. Automated verification uses synthetic data and mocked providers;
  live provider/browser ranking verification is not claimed.

## Planned — future functionality

- `backend/app/agents/` contains four bounded workflow packages: `jd`, `screening`, `copilot`, and `evaluation`. The `jd` package has the trainer-demo workflow described above; `screening` has preparation, hybrid evidence matching and hard-requirement decisions. `copilot` and `evaluation` remain planned. These are Python modules inside the FastAPI modular monolith, not separate microservices.
- Other ORM business models, a production Docker Compose PostgreSQL service, and other repositories remain planned. The disposable database used for the successful live validation does not implement the production service.
- A production policy ingestion service, recruiter/admin uploads, active/approved policy selection and replacement/deletion lifecycles for obsolete versions remain planned. The semantic JD path requires one explicitly configured stored document/version; there is no automatic active/latest selection. CVs and transcripts do not belong in either knowledge collection. Production Docker Compose remains planned as noted above.
- Background processing and integrations other than the implemented LLM and MCP job-publishing paths remain planned; their packages are architectural boundaries only.

Production access governance, candidate/application persistence, formal human approval/revision, the remaining hiring workflows, publication audit/deduplication and additional external publishing destinations remain planned work. Recruiter authentication, owned job records and conversation history are implemented in this branch, subject to the deployment/validation limits documented above.


## Implemented - F2 scoring integration; live synthetic validation completed

`schemas/candidate_score.py` defines validated weights and score breakdowns;
`services/candidate_scoring.py` derives scores from existing validated Screening
evidence. The authenticated batch API adds server-calculated scores; the CV UI
reviews weights with criteria and displays eligible-only weighted-score ranking,
breakdowns and separate not-scored cases. Hard-requirement decisions and the
original requirement-count ranking contract are preserved.
Migration `0003_candidate_scores` adds reviewed job weights and owner-linked
revision/version-bound score records. Fresh disposable PostgreSQL migration/default
checks passed on 12 October 2026; the office demo database was not migrated.
Earlier sections describe their individual increments; weighted scoring is now
implemented and live-verified with synthetic data on 12 October 2026. Policy assumptions, offline/automated
test boundaries and manual verification are in [F2 scoring](f2_scoring.md).

[LiveKit feasibility](livekit_feasibility.md) documents a possible isolated
audio/video proof. Its later implemented synthetic Cloud proof is described below.

## Implemented - F3 recruiter selection and scheduling

Eligible screening cards support explicit human selection and provider-independent
interview scheduling. Owner-protected create/list APIs reread current approved F2
records; eligible-but-unscored selection requires extra confirmation. Migration
0004 stores UTC/IANA timezone, duration and revision-bound selection references.
Fresh disposable PostgreSQL migration/API and real browser/Groq-backed screening-to-
scheduling checks passed on 12 October 2026. Saved history loads after page reload
without recovering in-memory screening results. Calendar, email, recording and candidate
accounts are not implemented. Candidate bearer invitation access is described below.
See [interview scheduling](interview_scheduling.md).

## Implemented - F3 Increment 2A synthetic LiveKit Cloud proof

Owner-protected short-lived token issuance and a lazy React interview page connect
two recruiter-controlled synthetic test sessions for camera/microphone media only.
The SDK credentials stay server-side; opaque IDs, strict grants and no-store tokens
protect access. No new workflow or database migration is added. Two Edge clients
passed real Cloud synthetic A/V, mute/camera and cleanup checks. In-app connection,
physical devices and production candidate access remain unverified/planned as
specified in [LiveKit interview proof](livekit_interview_proof.md).

## Implemented - F3 Increment 2B candidate invitations

`interview_access.py` adds owned invitation generation/revocation and public
single-use exchange into a hashed HttpOnly candidate session. Migration 0005
stores hashes only. Recruiter/candidate room identities are distinct; both token
paths enforce a bounded schedule window and current criteria. Cloud removal
revokes candidate room access. The shared React media page includes invite/copy/
revoke controls; `/interview-join` bypasses recruiter login using invitation
authorization, not an authentication bypass. New disposable PostgreSQL, real
API concurrency/revocation and two-role synthetic Edge media checks passed.
Physical devices and production candidate deployment remain unverified/planned.
See [Interview invitations](interview_invitations.md).
