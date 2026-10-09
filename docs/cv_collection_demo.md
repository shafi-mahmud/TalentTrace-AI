# External CV collection demo

## Implemented - external CV collection demo path, once configured

TalentTrace can publish a job with an optional server-configured application
link: chat JD draft -> FastAPI -> official MCP client -> `publish_job` ->
Discord **Apply for this role** -> Google Form -> form owner's Google Drive.
The TalentTrace-side link plumbing is implemented and tested with mocked
Discord traffic. On 07 Oct 2026, the project owner confirmed manual verification
of UI-to-MCP-to-Discord publication and Discord-to-Google-Form-to-Sheets/Drive
CV collection. Form setup remains manual; this external channel does not
automatically ingest Drive uploads into TalentTrace. The separate
[native CV intake foundation](cv_ingestion.md) now accepts manually selected
sample files, without parsing or screening.
Google Form/Drive is an external privacy dependency, not a TalentTrace database.

`APPLICATION_FORM_URL` comes only from backend settings (environment or ignored
root `.env`). Recruiter requests and LLM output cannot supply or override it.
It is optional: without it publication has no Apply field. The backend returns
only destination/status/external_id; the frontend does not receive the URL.
The standalone MCP contract accepts an optional validated `application_url`
from trusted clients. It is not an authorization mechanism for untrusted clients.

Validation accepts public-looking HTTPS URLs up to 2048 characters, without
userinfo, fragments, unsafe controls or nonstandard ports. It does not fetch
URLs, resolve redirects/DNS, prove form ownership or verify that a form exists.
The operator must choose the approved responder URL. Discord's stricter
1024 UTF-16 field limit and 6000 total embed limit also apply; oversized
publication fails rather than truncating a link or job.

## Recommended - manual Google Form setup

1. In the form owner's personal My Drive, manually create a form titled
   **TalentTrace AI - Job Application Demo**. Do not automate creation.
2. Add required fields:
   - **Job Reference**: short answer. Candidates copy the exact **Job Reference**
     displayed in the Discord circular, such as `TT-JOB-30BB2CDF9A5CCCA9`.
   - **Candidate Name**: short answer; synthetic name only for evaluation.
   - **Email**: short answer with email response validation; synthetic test data.
   - **CV / Resume**: file upload, one file, preferably PDF-only for this demo,
     with a reasonable offered limit such as 10 MB. If enabling document uploads,
     verify a synthetic DOCX is accepted; do not claim DOCX-only filtering.
   - **Consent**: required checkbox. Example wording: "I agree that my synthetic
     application details and sample CV are stored in the form owner's Google
     Drive for the TalentTrace recruitment/evaluation demonstration."
3. Review respondent access and publish/share the **responder URL**, not the
   editor URL. Restrict form editors and the upload folder to trusted reviewers.
   Do not make the CV folder publicly accessible.
4. File-upload respondents need Google sign-in. Uploaded files are stored in
   a new folder in the form owner's Google Drive. File-upload questions cannot
   be used when the form is stored in a shared drive or administrator DLP blocks
   them. Confirm the account supports this before the demo. See
   [Google's file-upload guidance](https://support.google.com/docs/answer/7322334?hl=en-ae).
5. Copy the HTTPS responder URL into ignored root `.env` locally:
   `APPLICATION_FORM_URL=<real HTTPS form URL>`. Never commit the real URL.
   Restart the existing backend because settings are loaded at startup.

## Recommended - one manual end-to-end trainer verification

1. Keep the existing PostgreSQL/demo-policy environment; do not reseed or migrate
   merely to test the form link. Start/restart the backend with its existing
   virtual environment and start the existing frontend normally.
2. Generate a synthetic JD clearly marked **NOT A REAL VACANCY** in the chatbot.
   Review the draft and use its explicit **Publish to Discord** confirmation once.
3. In Discord, verify **Job Reference** immediately before **Apply for this role**.
   Copy that reference into the form when submitting. Publication is a
   real external, non-idempotent action. There are no automatic retries or server
   deduplication. If delivery is uncertain, check the channel before any retry.
4. Follow the link, sign in with an appropriate demo Google account, and submit
   **one** synthetic application and sample CV. Keep the CV outside this repository.
5. Open the form owner's Drive upload folder and verify the sample file was
   collected. This proves external collection, not TalentTrace ingestion.

Every published demo circular contains a bounded **Job Reference**. The
TalentTrace backend supplies `TT-JOB-` plus 16 uppercase hexadecimal characters
from the owned persistent job UUID. Draft revisions keep that job reference;
recruiter payloads and LLM output cannot supply a reference. The standalone MCP
contract still requires trusted clients to provide their own safe reference of
at most 40 characters; its fixed manual smoke job uses `TT-DEMO-SMOKE-001`.

The new owned-job code replaces the prior content-derived reference in the
TalentTrace API path. Its live database migration is not yet verified; see
[recruiter job ownership](recruiter_job_ownership.md). This is not publication
idempotency or candidate/application persistence. Automatic form prefilling
remains planned. The configured form is shared across publications; reference
entry is manual, and Google Form submissions are not synchronized into native
candidate records or routed automatically per job.
The frontend success state reports publication metadata only and does not
claim that a form is configured or an application has been received.

## Privacy boundaries and Planned functionality

Use synthetic/sample candidate information only during development/evaluation.
Never commit CVs, candidate names/emails, Drive files, real form URLs or secrets.
Do not put candidate information in application logs, LangGraph thread IDs,
JD Agent inputs or MCP publication fields. This link feature does not add a
comprehensive personal-data detector. Future scoring must not use protected
demographic attributes. Google Form/Drive access and manual deletion are the
operator's responsibility; production retention/deletion automation is absent.

**Planned - not implemented:** native candidate application portal, Google Drive
API synchronization, automatic CV import, candidate database persistence,
screening LangGraph, scoring/
ranking, candidate authentication, retention/deletion automation, production
approval/audit, and additional publication destinations. No Google OAuth,
Drive API or candidate-processing dependency was added.

Native upload, primary digital extraction, OCR fallback and grounded candidate profiles
are implemented separately;
see [native CV ingestion](cv_ingestion.md). This does not import Google Drive data.
