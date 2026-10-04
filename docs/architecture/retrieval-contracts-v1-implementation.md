# Retrieval contracts v1 implementation note

**Status:** Foundation implemented; runtime migration remains disabled.

This milestone introduces immutable retrieval/index contract primitives required
by the approved Balanced Multilingual migration architecture.

## Implemented

- Immutable `EmbeddingSpaceContract`
- Independent immutable `MaterializationContract`
- Deterministic `space_sha256`
- Deterministic `materialization_sha256`
- Safe collection-name derivation from embedding-space identity
- Immutable authorized read scope
- Distinct trusted generation write scope
- Immutable resolved retrieval-index identity
- Explicit `legacy_unverified` representation for the current `rag_documents`
  serving path
- Fail-closed compatibility guards for:
  - embedding-space mismatch
  - materialization mismatch
  - generation mismatch
  - vector dimension
  - finite vector values
  - normalization
  - collection/space binding
- Internal reviewed candidate registry for the pinned BGE-M3 dense contract

## Reviewed BGE-M3 candidate

The internal candidate registry contains:

- Profile: `balanced-multilingual@1`
- Model: `BAAI/bge-m3`
- Revision: `31e47391fcbda65be526abe98e646b3c6cd845a8`
- Dimensions: 1024
- Maximum input: 8192 tokens
- Dense cosine retrieval
- Normalized embeddings
- No query/passage prefix
- `runtime_enabled = false`
- `selectable = false`

This registry entry is metadata only. It does not load BGE-M3, create a Qdrant
collection, index documents, or enable profile switching.

## Production behavior remains unchanged

Production continues to use:

- `sentence-transformers/all-MiniLM-L6-v2`
- legacy `rag_documents`
- `RAG_TOP_K=3`
- `modAIJet:latest`

The existing `rag_documents` collection remains explicitly unverified with
respect to immutable model revision/materialization provenance. This milestone
does not fabricate a verified generation for it.

## Explicitly not implemented

This milestone does not add:

- database schema changes
- Alembic migrations
- workspace retrieval assignments
- index generations
- transactional source outbox
- generation-aware Qdrant runtime
- shadow indexing
- BGE-M3 production loading
- BGE-M3 activation
- activation/rollback APIs
- migration UI
- live document reindexing
- production profile switching

## Validation

The implementation is covered by deterministic unit tests for contract hashing,
scope validation, vector-space isolation, candidate inactivity, legacy state,
collection identity, and fail-closed vector validation.

The next milestone is:

**generation schema + transactional source outbox**

That milestone remains separately reviewed and must not activate BGE-M3.
