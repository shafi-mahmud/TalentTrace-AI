# Technical reference grounding

Implemented: `CuratedTechnicalRetriever` replaces the default three synthetic
facts with five short, attributed summaries. These are paraphrases, not copies
of whole manuals, company policy or model-generated reference facts.

| Document | Version / section | Topics |
|---|---|---|
| [Python tutorial](https://docs.python.org/3.13/tutorial/datastructures.html) | 3.13, More on Lists / Tuples and Sequences | List mutability; tuple immutability |
| [Python asyncio](https://docs.python.org/3.13/library/asyncio-task.html) | 3.13, Coroutines | Awaiting and scheduling coroutines |
| [PostgreSQL tutorial](https://www.postgresql.org/docs/18/tutorial-transactions.html) | 18, Transactions | Commit and rollback |
| [HTTP semantics](https://httpwg.org/specs/rfc9110.html#GET) | RFC 9110, 9.3.1 | GET semantics |

Each reference retains a stable claim ID, document ID, title, section, version,
URL, provenance and retrieval basis. A corpus hash versions durable analyses.
Aliases provide bounded topic retrieval; they do not prove the candidate's claim.
Correct, incorrect, negated and incomplete answers can retrieve the same source.
The graph separately assesses them and validates exact transcript/reference
quotations. Unsupported citations fail validation. Missing references require
technical accuracy to remain uncertain/not assessed.

Implemented default: local lexical/alias retrieval. Optional
`TECHNICAL_REFERENCE_MODEL_PATH` reuses the existing BGE embedding service with
a pre-downloaded local SentenceTransformer directory. It does not download a
model, add a vector database or send text to an embedding provider. Semantic
matches require a domain anchor and threshold. Tests exercise that boundary with
mock embeddings; actual BGE model inference is not yet verified in this sprint.

Known conflicting duplicate claim IDs cause abstention. Explicit obsolete
versions and unrelated language/database topics are rejected by conservative
filters. This is a small reviewed corpus, not general technical coverage or a
complete contradiction detector. A new language/version needs reviewed sources.
Model interpretations remain advisory and distinct from reference summaries.
