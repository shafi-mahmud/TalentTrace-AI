# Native CV intake and primary digital-text extraction

## Implemented

WBS #647485 has a deterministic upload slice, not an agent or candidate parser:
**CV Intake UI -> multipart FastAPI endpoint -> file/package validation ->
private local storage -> safe batch/upload identifiers.** The JD Assistant stays
the default view. Switching modes preserves its in-page conversation.

`POST /api/v1/cv-uploads` accepts `multipart/form-data` with exactly one
`job_reference` text field and repeated `files` parts. A successful HTTP 201
response contains only status, Job Reference, UUID batch ID, accepted count and
each file's UUID/type/byte size. It never returns original filenames, file
contents, hashes or storage paths. The browser shows selected names/sizes locally
and sends File objects without rendering or extracting their contents.

The reference must match `TT-JOB-` followed by 16 uppercase hexadecimal characters.
It is syntactically validated only. There is no authoritative persisted job
profile, foreign key, candidate record or verified job ownership.

## Validation and resource limits

- 1-20 PDF/DOCX files; nonempty, at most 10 MiB each and 100 MiB document bytes
  per batch. Files are copied in 64 KiB chunks inside a worker thread, rather
  than reading the whole batch into application memory.
- Multipart parsing is bounded to 20 files, one field and a 1024-byte text part.
  An actual received-body limit of 101 MiB includes multipart overhead and works
  without Content-Length. Starlette spools uploaded files and closes temporary
  handles when parsing fails or the form context exits. Parser limits are not
  a replacement for deployment-level request limits/concurrency controls.
- Extensions and MIME types must agree: PDF's standard MIME or octet-stream,
  DOCX's standard OOXML MIME or octet-stream. MIME is a signal, not trusted proof.
- PDF requires a version header and an EOF marker near the end. This is signature
  validation, not a complete PDF parser or a guarantee the document is harmless.
- DOCX requires a ZIP local header, readable ZIP directory, nonempty
  `[Content_Types].xml` and `word/document.xml`. Reject duplicate/unsafe paths,
  encryption, unsupported compression, macros/embedded-object members and
  suspicious package sizes. Conservative limits are 2000 members, 50 MiB total
  declared uncompressed size, 10 MiB per member and compression ratio 100:1.
  No members are extracted or decompressed; XML semantics and CRCs are not
  verified. These checks are not malware scanning or CV parsing.
- Raw unsafe filenames are rejected (paths, drive/UNC separators, controls or
  more than 255 characters). Some multipart clients normalize Windows paths to
  basenames first. Either way, original names never influence stored filenames.

## Private storage and rollback

Default: ignored `data/cv_uploads/`, relative to the repository root.
Optional `CV_UPLOAD_ROOT` in local environment/ignored root `.env` can choose
an external private path; relative paths resolve from the repository root.
Repository-local overrides must stay under `data/`, not frontend/docs/RAG/tests.
Import/startup creates no upload folders. Existing ignore rules already cover
`data/`; no sample CVs or binary fixtures are tracked.

Layout: `<private-root>/<job_reference>/<batch_uuid>/<upload_uuid>.pdf|.docx`.
There is no download/static-serving endpoint. Newly created upload directories
request owner-only POSIX permissions. On Windows, verify inherited ACLs restrict
the storage directory to the trusted application operator. There is no encryption
at rest, authentication, tenant isolation or production privacy-compliance claim.
A future Docker named volume can mount at the configured path; it is not wired yet.

One invalid file or write failure rejects the batch and removes the directory/files
created for that batch. Prior successful batches are untouched. Empty parent
directories may remain. This is filesystem cleanup, not a database transaction;
process crashes or cleanup-permission failures can leave artifacts requiring
operator cleanup. Storage errors are fixed public messages with no raw paths.
Uploads are not idempotent. An interrupted response may leave a successful batch;
check with the operator before retrying. Retention/deletion automation is planned.

## Implemented - primary extraction (#647488)

After upload, **Extract text** calls
`POST /api/v1/cv-uploads/{job_reference}/{batch_id}/extract`.
The synchronous service runs in the API threadpool, reads only that private batch
and leaves every original unchanged. It rejects symlink/junction job directories,
batch directories and files, unexpected filenames, nonregular files, empty batches
and storage limits. Filenames must be canonical upload UUIDs with `.pdf`/`.docx`.
Files are processed in filename order. Missing batches return a fixed 404;
invalid identifiers, unsafe layouts and unexpected service failures have sanitized
request-level errors. There is no client-supplied filesystem path.

**PDF:** PyMuPDF 1.26.7, using `pymupdf`, extracts `get_text("text", sort=True)`
page by page. Internal evidence retains actual 1-based page numbers, including
empty pages. Line endings are normalized and unsafe control/format/surrogate
characters removed, keeping tabs/newlines. No OCR, image rendering, semantic
rewriting, embedded-content execution or external-link following occurs.
PDF calls are serialized with a lock because concurrent MuPDF thread use is unsafe.
Parser diagnostics are suppressed during these calls and raw exceptions are not
returned or logged.

**DOCX:** existing python-docx walks `iter_inner_content()` in paragraph/table
order, then row/cell order. Nonempty paragraphs become ordered evidence blocks;
paragraphs within cells are `table_cell` blocks. Merged cells are visited once and
nested tables are traversed once. Block indexes start at 1. This does not interpret
comments, tracked changes, images, macros or external hyperlinks. DOCX headers,
footers and text boxes are not part of this body-text increment.

Internal frozen `ExtractedCvDocument` results hold text, character count and
`PdfPageText`/`DocxTextBlock` evidence only in memory. They are separate from the
public response contract; text/evidence is omitted from object representations.
No extracted text is written to sidecars, a database, logs, RAG or browser state.
The API returns `status=processed`, Job Reference, batch ID, processed count and
per-file upload ID, type, extraction status, character count, source-unit count
and `ocr_recommended`. The UI displays pages/blocks and safe status only.

### Digital-text sufficiency heuristic - not OCR

A PDF is `text_extracted` only when it has **at least 80 alphanumeric characters
in total** and **at least 50% of pages each contain at least 20 alphanumeric
characters**. Otherwise it is `ocr_required` with `ocr_recommended=true`.
Equality meets the threshold. Character counts in API metadata include whitespace;
the heuristic counts letters/digits only. This is a routing heuristic, not reliable
proof that a PDF is scanned: short digital CVs may trigger it, and mixed image/text
documents can still pass. Text ordering in complex columns depends on the parser.

`ocr_required` means digital extraction was insufficient; it is **not evidence
that the candidate lacks information**. A future candidate parser must not run
normal parsing on these PDFs without successful OCR evidence. The UI offers
**Run OCR** after primary extraction.
DOCX never routes to OCR; no alphanumeric text gives `extraction_failed`.
Malformed, encrypted or resource-limited documents also report a safe per-file
`extraction_failed`, without deleting the batch or affecting other files.
Unlike upload rollback, extraction processes an already stored batch independently.

Extraction limits are 200 PDF pages, 500,000 total normalized text characters per
document, 10,000 nonempty DOCX blocks and nesting depth 16; existing upload/ZIP
limits are rechecked. These are application limits, not a parser sandbox, malware
scanner, hard timeout or protection against every hostile document. Storage must
remain operator-controlled; concurrent filesystem replacement is not supported.

## Implemented - OCR fallback (#647491)

`POST /api/v1/cv-uploads/{job_reference}/{batch_id}/ocr` reuses the same validated
stored-batch lookup and primary extraction. Only PDF `ocr_required` results are
eligible. Digital `text_extracted`, malformed `extraction_failed` PDFs and all
DOCX files bypass OCR. If none qualify, a successful no-op has
`attempted_count=0` and `files=[]`, without checking OCR installation.

For eligible PDFs, pages with at least 20 alphanumeric digital characters are
preserved; other pages use PyMuPDF's integrated Tesseract
`get_textpage_ocr(language="eng", dpi=300, full=True, tessdata=...)`.
If every page passes the page threshold but the document fails the total threshold,
all its pages are OCRed. Each selected page runs once per request, using full-page
OCR and deterministic TextPage extraction. English only; no confidence scores.
300 DPI favors readable recognition at greater CPU/memory cost than lower DPI.

Internal frozen page evidence records `source_method=digital|ocr`, 1-based page
numbers and normalized text in document order. It remains backend memory only.
Original PDFs are never rewritten and no OCR layers or sidecars are saved.
Public responses contain batch identity, `attempted_count` and eligible files'
upload ID, `ocr_status`, character count, total page count and OCR page count.
The count represents eligible files processed, including resource-limit failures;
`ocr_page_count` counts page calls actually attempted, including failed calls.

`ocr_extracted` requires the same document-level 80-character/50%-of-pages
sufficiency checks plus at least one OCR page recovering 20 alphanumeric characters.
Blank/negligible recognized text, parser failures or resource-limit violations
return per-file `ocr_failed`; failure discards partial evidence. Other files and
originals remain intact. OCR output is untrusted extraction evidence, not verified
candidate truth. Failure is not evidence of missing qualifications.

Limits: **25 total pages per eligible document**, **100 eligible PDF pages per
batch**, **25 million rendered pixels per selected page** at 300 DPI, and the
existing **500,000-character output limit**. The batch budget counts preserved
pages too, conservatively. Later over-budget files report `ocr_failed` without OCR
calls. Digital and OCR access share the same serialization lock; work runs in the
API threadpool. Native OCR stderr is temporarily suppressed during engine calls
to avoid logging paths or parser details, then restored. This also briefly
suppresses unrelated stderr writes in the same process. There is no hard timeout,
worker queue or parser sandbox; production isolation/concurrency design is planned.

### System dependency and local setup

PyMuPDF remains pinned at 1.26.7; no additional Python OCR library is required.
Tesseract OCR with readable, nonempty English `eng.traineddata` is an external
system/data dependency. PyMuPDF uses its integrated OCR engine and the installed
language files; it does not invoke the Tesseract executable to OCR each page.
Optional `OCR_TESSDATA_PATH` chooses the language-data directory; otherwise
PyMuPDF attempts local discovery. Resolution is lazy, only when files need OCR.
Missing configuration/data yields fixed **503 `ocr_not_configured`**:
“OCR processing is not configured.” Corrupt nonempty language data can still fail
at engine initialization and produce `ocr_failed`; existence is not proof of validity.
Normal startup, JD/MCP, uploads and digital extraction do not require OCR setup.

**Local verification on 07 Oct 2026:** Tesseract was unavailable on PATH and at
the checked standard Windows install locations; PyMuPDF could not discover
English data. Mocked deterministic tests validate fallback behavior, but real
OCR verification is **Blocked**, not passed. No system software was installed.

Recommended manual setup: install Tesseract with English data explicitly, verify
`tesseract --version` and `tesseract --list-langs` includes `eng`, then either make
discovery work or set `OCR_TESSDATA_PATH` in ignored local `.env` to its tessdata
directory. Restart only the backend after changing configuration. Never place a
machine-specific active path or candidate documents in Git.

The CV Intake UI retains upload and digital-extraction status, offers **Run OCR**
only when needed, disables duplicate attempts while running, and shows compact
OCR extracted/failed page metadata. Missing setup shows “OCR is not configured
on this server.” No recognized text or installation details enter browser state.

## Recommended synthetic verification

1. Restart the local backend after adding this route/configuration. Keep the
   existing JD/RAG/MCP environment; do not reseed or republish for upload testing.
2. Open the existing frontend and choose **CV Intake**. Copy a published demo
   Job Reference into its input.
3. Select 1-20 synthetic PDF/DOCX files generated outside the repository. Remove
   unwanted selections, then upload once.
4. Verify accepted count and opaque batch reference. Click **Extract text** and
   check PDF pages/DOCX blocks. A synthetic blank PDF should show **OCR required**.
   Public responses must contain metadata only. Check only this batch's generated
   filenames locally; do not display or log candidate contents.
   With OCR configured, use an image-only synthetic PDF, click **Run OCR**, check
   **OCR extracted**, and confirm its original bytes are unchanged.
5. Remove temporary synthetic input files and, when no longer needed, only the
   synthetic batch created by this test. Never delete unrelated upload data.

Automated tests generate synthetic documents in memory and store only in pytest
temporary directories. They cover mixed/20-file batches, limits, signatures,
package safety, traversal, opaque responses and rollback. Extraction tests cover
real synthetic parser output, page/block order, OCR thresholds, malformed files,
metadata-only responses and byte-identical originals. No real CVs, provider
calls, Google data or binary repository fixtures are used.

## Separate external channel and Planned work

The already verified [Google Form/Drive collection demo](cv_collection_demo.md)
remains separate. This native file picker does not automatically import Google
Form, Sheet or Drive data. CVs never enter Company Policy/Technical Knowledge
RAG, the JD Agent, MCP publication or LangGraph thread IDs in this slice.

**Planned - not implemented:** structured candidate
parsing, candidate database records, background processing, screening LangGraph,
scoring/ranking, automatic Drive import, authentication/authorization, malware
scanning, production retention/deletion and Docker named-volume integration.
Use only synthetic/sample CVs in the trusted localhost demo.
