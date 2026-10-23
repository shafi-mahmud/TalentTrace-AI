# Recruiter application analytics

## Implemented service

The authenticated job applications API reconciles local validated upload files
with the trusted external-import ledger using `(batch_id, upload_id)`. An imported
file present in both stores counts once as a trusted import. Scoring tables are
not read and running screening cannot create another received application.

New means this job/application identity has not been explicitly marked viewed.
Acknowledge requests contain only the displayed identities. The service validates
that snapshot against current identities and inserts acknowledgement rows with
conflict handling; repeat acknowledgement is safe. Later arrivals stay new.
Native files that have disappeared cannot be historically counted without an
intake ledger; imported identities remain counted with unavailable-file warnings.
File availability checks type/size/signature, not a fresh cryptographic digest.

Ownership is checked before discovery or acknowledgement. No CV text, filenames,
contact data, external source IDs or credentials are returned. Listing is bounded
to 1,000 identities; exceeding bounds fails instead of returning partial totals.
Invalid native batches are excluded with a warning. These are local workspace
counts, not counts from a live Google Forms or LinkedIn query.

## Migration compatibility and verification

The existing `0011_application_views` migration is reused unchanged; the single
current head remains `0016_submission_deletion`. No migration was executed against
an existing database. The model is registered in the current backend.

Initial service validation: 12 backend tests passed, one opt-in disposable
PostgreSQL test skipped; 3 frontend API tests passed. Authorization tests use real
authentication/ownership handlers with SQL doubles; acknowledgement tests use
statement doubles. PostgreSQL concurrency/durability acceptance is not inferred
from those doubles. No external calls were made.
