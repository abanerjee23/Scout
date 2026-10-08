# Local policy assistance evidence

8 October 2026. Engineering validation uses real PostgreSQL 17/pgvector 0.8.6 and explicit fake embedding/answer adapters. No provider quality is inferred.

Nine API/index/lease cases pass, covering exact cosine retrieval with approved version/hash filters, mandatory rule passages, valid/invalid citations, duplicate requests, stale revisions, manager privacy, missing index and explicit full-policy baseline. Four migration/cap/read regressions pass. Text-embedding-3-small at 1536 dimensions and the fixed receipt model are pinned; source indexing and questions consume the same persistent conservative budget as extraction.

Sources: [OpenAI embedding documentation](https://developers.openai.com/api/docs/guides/embeddings), [pgvector](https://github.com/pgvector/pgvector). Portable embedding storage is cast to the provider extension's schema-qualified vector type for exact cosine search. The small clause set needs no approximate index. Packaged governing text remains authoritative; index content cannot introduce a new passage. Source snapshots are immutable and verified against their hash.

Remaining release evidence: actual model/embedding access; RAG versus full-context answer/citation scoring on the frozen unseen release set; zero critical false permission; actual cost and latency; minimized Galileo trace receipt; approved policy activation. A valid quote is a structural check, not proof that an answer is factually correct.
