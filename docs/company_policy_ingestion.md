# Local Company Policy file ingestion

## Implemented

An explicit operator CLI extracts one local PDF, DOCX, TXT or Markdown file and
validates it as a `CompanyPolicySource`. It then reuses
`ingest_company_policy_source()` for the existing heading-aware 400/50 BGE-token
chunking, normalized 384-dimensional BGE document embeddings and atomic
PostgreSQL/pgvector persistence. Extraction does not connect to a database,
create embeddings, call an LLM or follow web resources. No migration is required.
The JD graph, query embeddings and exact cosine retrieval remain unchanged.

**Implemented and verified — 07 Oct 2026:** 44 focused extraction/CLI tests and
347 complete backend tests passed. Real temporary synthetic DOCX and four-page
text PDF files outside the repository were ingested through the actual CLI into
the preserved local demo PostgreSQL/pgvector container. Each stored the expected
source/version/hash metadata and normalized 384-dimensional BGE vectors. A fresh
process selected each new document UUID and the actual FastAPI endpoint ran
LangGraph -> BGE -> pgvector -> Groq, returning HTTP 200, semantic mode, a draft
requiring human review and one citation belonging to that external source.
Strict structured output was accepted. Re-ingesting the DOCX source/version
failed with the controlled duplicate message and no extra document. The original
selected demo policy, hash and three chunks were unchanged; `.env` was not edited.
Temporary source files were removed; the container and two synthetic smoke
policy versions remain preserved. This is backend validation, not UI upload.

From `backend/`, install the project's pinned requirements into its existing
virtual environment if needed. PostgreSQL/pgvector and the existing knowledge
tables must already be available. Keep database credentials in ignored local
configuration; the CLI never edits `.env`.

**Example — synthetic policy outside the repository, PowerShell:**

```powershell
.\.venv\Scripts\python.exe -m app.rag.ingest_policy_file `
  --file "C:\Policies\synthetic-company-policy.docx" `
  --title "Example Company Hiring Policy" `
  --version "2026-01"
```

Success prints only:

```text
Policy ingestion succeeded.
source_id=<logical-source-uuid>
document_id=<stored-version-uuid>
```

- `source_id` identifies the logical policy source. Omission generates a UUID.
  For later versions of the same policy, explicitly reuse the returned UUID
  with `--source-id <logical-source-uuid>`.
- `--version` identifies the operator-supplied logical version. Repeating the
  same source/version is rejected without overwriting or partially saving it.
- `document_id` identifies the stored database row for that version. Set
  `COMPANY_POLICY_DOCUMENT_ID` to this UUID in local configuration or process
  environment, then restart the backend to select it explicitly. No latest,
  approved or active policy is chosen automatically.
- Identity is never derived from a file path or filename. Source title and
  version use the existing contract validation; the collection is company_policy.

## Extraction boundaries and safety

- Extension allow-list: `.pdf`, `.docx`, `.txt`, `.md`, case-insensitive.
- Regular files only; maximum **5 MiB**, checked before reading and with a
  bounded read. Empty files, invalid encodings and blank text are rejected.
- Extracted text is bounded to the existing **500,000-character** limit.
  Existing normalization preserves headings, normalizes line endings and tabs,
  removes surrounding/trailing whitespace and validates unsafe control characters.
- PDF: strict local text extraction in page order, maximum **200 pages**;
  relevant decoded-stream limits are **8 MiB**. Password-protected files are
  rejected unless an empty password opens them without supplied credentials.
  Blank/image-only pages provide no text; wholly textless PDFs fail with an
  explicit OCR-not-implemented message. Mixed PDFs may omit image-only pages.
  PDF heading styles are not reconstructed; extracted textual headings are
  retained as supplied by the parser. No OCR, scripts or embedded actions run.
- DOCX: document-body paragraphs and top-level tables retain block order.
  Standard Heading 1–6 styles become Markdown headings. Simple table rows use
  cell separators, and merged cells are not duplicated within a row. Images are
  ignored. Expanded ZIP content is bounded to **20 MiB / 2,048 entries** before
  parsing; encrypted or macro-containing archives are rejected.
- TXT/Markdown: UTF-8, optionally with a UTF-8 BOM. Markdown headings remain
  intact. No Markdown rendering, URL fetching or instruction execution occurs.
- Errors and CLI output omit document contents, filesystem paths, SQL,
  credentials and vectors. Parser/model diagnostics are suppressed during CLI
  execution. Importing the application or CLI does not read an external file,
  load BGE, create a database engine, connect or ingest anything.
- This is a bounded local/preload command, not a sandbox for hostile uploads.
  Parser limits reduce resource risk but are not a total memory/time guarantee.
  Complex DOCX layout, headers/footers, nested tables and tracked-change
  reconstruction are outside this increment.

Use only approved company-policy text. Never ingest CVs, transcripts, candidate
personal data or credentials; the extractor does not classify document content.
Keep confidential inputs outside Git. `.gitignore` is not a guarantee for all
text formats or already tracked files. Inputs are not copied into the repository.
Selecting an externally ingested policy for JD generation sends retrieved policy
excerpts to the configured Groq provider, as in the existing JD workflow; ensure
that use is authorized. Policy text remains untrusted reference data.

## Documented model decision

Keep `BAAI/bge-small-en-v1.5` for this increment: the current English demo corpus
is small, its ingestion/retrieval path is already verified, and the database
stores `Vector(384)`. Replacing the model is a separate schema/model-identity
and re-embedding decision, not a file-loader change. BGE-small is not claimed
to be universally superior.

**Planned evaluation:** benchmark the current BGE-small baseline against
`BAAI/bge-m3` and optionally `Qwen/Qwen3-Embedding-0.6B` on TalentTrace retrieval
quality, latency, memory/model-load cost and migration cost. No alternative
models were added or downloaded. Sparse/ColBERT retrieval is not implemented.

## Planned

Recruiter/admin upload UI, approved/active policy lifecycle, scanned PDF OCR,
legacy `.doc`, URL/web ingestion and model benchmark/migration remain planned.
The current frontend retains its existing synthetic-demo presentation; this
increment adds no UI upload or production/private-policy management.
