# Balanced Multilingual index migration and activation design v1

**Status:** Proposed design; implementation requires a separate approved milestone
**Scope:** Workspace-scoped retrieval profile assignment and safe full-index replacement
**Baseline reviewed:** `8806e755abb0b862634e5a95d1887db76cf9b06e`
**Decision owners:** Product and platform engineering

## Decision record

The first production profile assignment should live at **Workspace** scope. A workspace owns one active retrieval generation; all Knowledge Bases selected by a RAG request must remain within that workspace, matching the existing authorization and query contract.

Keep logical profile names separate from immutable embedding contracts and physical index generations. MiniLM and BGE-M3 use separate Qdrant collections because their dimensions and embedding spaces differ. Within one contract collection, generation IDs, workspace IDs, organization IDs, Knowledge Base IDs, document IDs, and document versions are mandatory payload filters. PostgreSQL stores the authoritative workspace-to-generation pointer.

Build a replacement generation alongside the current generation. Record every document mutation in a transactional PostgreSQL outbox, replay changes into the candidate, validate it, then briefly fence workspace writes while catching up the final delta and switching the pointer in one PostgreSQL transaction. Keep the former generation current through a bounded rollback window using mirrored indexing. Retire and garbage-collect it only in a separate audited operation.

This proposal adds no runtime behavior. The first implementation would require schema, worker, API, Qdrant, UI, and acceptance work under separate review. This repository has no established ADR directory or ADR template; this document therefore contains the decision record and full architecture design in one place.

## Context and measured evidence

Production currently uses `sentence-transformers/all-MiniLM-L6-v2`, `RAG_TOP_K=3`, and generation model `modAIJet:latest`. The active Qdrant collection is the fixed name `rag_documents`. `EmbeddingService` lazily loads the one configured model from process settings; it normalizes vectors but does not resolve a per-request retrieval contract. `QdrantService.ensure_collection()` creates `rag_documents` if absent using the first vector's dimension. It does not bind that collection name to a model revision or validate a persisted space identity. The RAG pipeline embeds the question and searches this fixed collection.

The evaluation-only BGE-M3 benchmark used pinned `BAAI/bge-m3` revision `31e47391fcbda65be526abe98e646b3c6cd845a8`, MIT, dense dimension 1024, maximum input 8192 tokens, no query/passage prefix, cosine distance, and normalized vectors. Its safetensors file is 2,271,064,456 bytes. On the matched synthetic workload, query embedding plus retrieval median was 28.709 ms and process peak RSS was 1077.9 MiB. BGE-M3 improved the benchmark's cross-language retrieval, especially TR-query → EN-source, but these short fictional corpora do not establish customer-workload quality, long-document performance, answer quality, concurrency, or deployment capacity. See the [BGE-M3 benchmark](../../evaluation/experiments/compact-multilingual-bge-m3-v1.md) and [E5-base benchmark](../../evaluation/experiments/compact-multilingual-e5-base-v1.md).

The current production embedding service lives in `app/services/rag/embeddings.py`; the read-only logical profile catalogue is in `app/services/rag/retrieval_profiles.py` and `app/api/routes/retrieval.py`. It currently maps only the configured MiniLM identifier to a display profile. It does not bind a profile to an index. `app/services/qdrant.py` uses `rag_documents`, organization/workspace/Knowledge Base payload filters, and the `is_active` document-version flag. `app/services/rag/pipeline.py` performs one embed/search path, and the RAG route first authorizes all selected Knowledge Bases in PostgreSQL.

**Legacy-index prerequisite:** the existing `rag_documents` collection does not record the model revision, full preprocessing/chunk contract, or generation identity that created each point. The profile catalogue's benchmark MiniLM revision is not proof that the production cache loaded that exact snapshot. Before any generation-based activation, implementation must attest the running/source model artifact, vector dimension, preprocessing, chunking, and current payload/version coverage. If exact provenance cannot be established, represent the collection as `legacy_unverified` and keep it on the existing serving path while creating and validating a fully versioned MiniLM baseline generation. Only after an explicit cutover to that verified baseline can BGE-M3 migration begin. This can require one extra MiniLM rebuild; it is preferable to falsely certifying unknown vectors.

Indexing is asynchronous through Redis and `app/worker.py`. `DocumentVersion` and `IndexJob` identify document/version work; point IDs are deterministic for document/version/chunk. Replace temporarily indexes a new document version, then makes it active. Delete currently removes Qdrant points and source files before the database row is deleted. There is no durable document-change outbox, migration checkpoint table, generation identifier on points, or deletion tombstone. Redis is a queue, not the source of truth for an independent full-index migration. Those gaps matter for a resumable candidate build and are addressed in the future design below.

The enterprise hierarchy is Organization → Workspace → Membership → KnowledgeBase → Document. `resolve_knowledge_base_scope()` rejects selected Knowledge Bases outside one workspace. Existing authorization helpers are the gate for document and KB access. Profile/index selection must be added after this authorization succeeds and must not replace it.

Qdrant's current multitenancy guidance recommends payload partitioning for many tenants and notes the resource cost of creating many collections. This design uses one collection per immutable embedding-space contract, not one per tenant or workspace. Generations and tenant scopes are partitioned with indexed payload fields and mandatory query filters. This is a retrieval-safety design, not a claim that Qdrant filters replace application authorization. See [Qdrant multitenancy](https://qdrant.tech/documentation/manage-data/multitenancy/) and [collection management](https://qdrant.tech/documentation/manage-data/collections/).

## Requirements, invariants, and non-goals

The implementation must preserve these invariants:

1. An index generation binds exactly one immutable contract: model ID, immutable revision, dimensions, query preprocessing, passage preprocessing, normalization, distance metric, chunker/version/configuration, and generation ID.
2. Different embedding spaces never share a Qdrant collection or a query path. Dimension equality alone is not compatibility.
3. A candidate cannot receive product reads before integrity validation and explicit activation.
4. Each RAG request resolves one assignment snapshot once and uses that snapshot for its embedding implementation, dimensions, collection, generation filter, and source scope.
5. Activation changes one authoritative PostgreSQL pointer atomically. Requests already in progress may finish on the old generation; later requests use the new generation.
6. Rollback points to a retained generation; it does not require reindexing the entire corpus.
7. Organization, Workspace, Membership, Knowledge Base, active document-version, and source authorization remain independent of profile selection.
8. A failed or interrupted candidate build leaves the current active generation serving requests.
9. Missing, stale, or inconsistent profile/index metadata fails closed. No fallback may pair a query vector with a collection from another contract.

Non-goals for this design milestone: BGE-M3 runtime loading; production profile activation; profile selection UI; migration tables or Alembic changes; migration workers; outbox; dual indexing; new production Qdrant collections; document reindexing; activation/rollback APIs; and any change to `.env`, the current MiniLM configuration, `RAG_TOP_K`, or generation model. Do not add an Advanced Long-Document production profile: current evidence does not validate long-document quality.

## Logical profile, embedding contract, and index generation

These are separate identities. Names shown in the UI are not sufficient to select a model or collection.

| Layer | Example | Immutable fields | Purpose |
| --- | --- | --- | --- |
| Logical profile version | `compact@1`, `balanced-multilingual@1` | Stable product ID/version and human-readable policy | A supported product choice; not a Qdrant collection name |
| Embedding-space contract | MiniLM revision/dim 384 or pinned BGE-M3 revision/dim 1024 | Model ID, immutable revision, dimensions, query/passage transforms, tokenizer/preprocess contract, normalization, distance | Defines which query and document vectors are comparable |
| Chunk/index contract | chunker implementation ID plus size/overlap and metadata schema version | Chunking behavior, payload schema, index code contract | Defines exactly what content was indexed |
| Index generation | UUID plus workspace generation number | Embedding contract hash, chunk contract, corpus snapshot/event state | Identifies one workspace's materialized version of an index |

The profile registry initially contains only two reviewed logical versions:

- **Compact:** the current MiniLM path. Its “Compact” label is a product classification, not a claim of multilingual superiority; existing BGE evidence shows the current model is English-focused. The exact production artifact/revision is currently not attested by `rag_documents` or the runtime settings. Pin and verify the artifact for the first generation-based baseline; do not assume the evaluation-only `MINILM_BASELINE.revision` is what production loaded.
- **Balanced Multilingual:** BGE-M3 dense using only the benchmarked immutable revision and preprocessing contract. It remains unavailable until a separate implementation and production-readiness review.

Today the read-only catalogue calls the active MiniLM mapping `english-optimized`, while the `compact-multilingual` entry is an unverified placeholder. Implementation must resolve this registry/API compatibility explicitly: do not silently treat the placeholder as the active MiniLM contract or relabel API IDs without a versioned compatibility plan. A human-facing `Compact` name can map to the proven MiniLM artifact only after the legacy-index prerequisite above is satisfied.

The current read-only profile catalogue already contains an `Advanced Long-Document` placeholder with `not_configured` availability. This design adds no mapping, assignment, production support, or selectable migration action for that placeholder. New migration controls should include only reviewed Compact and Balanced Multilingual versions; decide separately whether to hide the existing placeholder from the read-only catalogue.

Profile versions map to an immutable serialized contract. Compute `contract_sha256` from canonical JSON with normalized key order and explicit schema version. Persist that JSON and hash with each generation so a future code release cannot reinterpret an existing index. A display-name change must not change the embedding-space ID. A model revision, dimensions, prefixes, normalization, distance, tokenizer, chunker, chunk settings, or payload schema change must create a new contract/generation.

The benchmark's per-request `K=3` is a retrieval policy, not part of the vector-space compatibility identity. Preserve production `RAG_TOP_K=3` during this design; a separately approved retrieval policy could change `K` without changing vectors. The chunking contract is part of the index generation because changing chunks requires reindexing.

## Profile assignment scope

| Scope | Security and user expectations | Operations, storage, rollback | Assessment |
| --- | --- | --- | --- |
| Platform-global | Simple and uniform; one tenant's choice affects all tenants | Fewest generations, but one migration blocks all organizations and cannot pilot independently | Too broad for a first enterprise rollout |
| Organization | Natural central policy; all workspaces in an organization follow one choice | Clear tenant owner; a pilot or exception requires duplicating the org-wide transition and handling workspace-specific content together | Possible later policy layer, but wider blast radius than needed |
| **Workspace** | Matches where users select sources and where membership grants access; one workspace can pilot without changing sibling workspaces | One assignment and migration scope per workspace; creates more generations than global policy but permits bounded rollout and rollback; collections remain shared by contract | **Recommended v1** |
| Knowledge Base | Fine-grained and flexible | A workspace RAG request may select multiple KBs, so it would need mixed-model query fanout/fusion or duplicate vectors into one shared space. This increases storage, complexity, and inconsistent answers | Reject for v1 |

One Workspace maps to one active generation, and every selected KB in one RAG request must continue to belong to that same workspace. Organization admins and workspace admins control profile migration. Workspace managers may inspect progress but cannot activate, roll back, or retire an index in v1; normal users see no infrastructure controls. Platform operators do not gain tenant data access from their global role: any support action must include an explicit workspace scope and audit actor.

## Physical Qdrant identity and isolation

Create one Qdrant collection for each exact embedding-space contract, shared across tenants using payload partitioning. A proposed collection name is `modai_space_<first-20-hex-of-contract-sha256>`. It contains no tenant name, model path, or user-provided text. Use a conservative lowercase ASCII alphabet (`a-z`, `0-9`, `_`) and a bounded length (for example, 64 characters); validate against the deployed Qdrant version before implementation. The full contract hash and full collection name live in PostgreSQL, not in a truncated name alone.

The collection's vector schema, distance, and contract are immutable after creation. A generation ID is a separate immutable identity/namespace; its materialized points change only through versioned, idempotent source events while it is active or retained for rollback. No in-place conversion of one generation's vectors to another contract is allowed.

The full physical index identity is the tuple:

```text
(qdrant_collection, contract_sha256, index_generation_uuid)
```

Every point contains at least:

```text
organization_id, workspace_id, knowledge_base_id,
document_id, document_version, source_revision,
chunk_index, index_generation_id, contract_sha256,
content_hash
```

Never store a vector without those identity fields. Create payload indexes for `organization_id`, `workspace_id`, `knowledge_base_id`, `document_id`, `document_version`, and `index_generation_id` as appropriate for the deployed Qdrant version. Every query filter must AND all of: authorized organization, authorized workspace, selected authorized KB IDs, exact resolved generation ID, and active source/version constraints. Do not permit unscoped search or a caller-supplied collection name.

MiniLM and BGE-M3 have different contract hashes and therefore different Qdrant collections. A `ResolvedRetrievalIndex` value passed through the request contains the verified contract, collection, generation, and tenant scope. Validate vector dimension, finite values, normalization, contract hash, Qdrant vector size, and cosine distance before search. If any check fails, return a safe service-unavailable error and alert; never retry against `rag_documents` or another model's collection.

Within one contract collection, candidate and retained generations coexist but remain logically isolated by the indexed `index_generation_id` filter and generation-scoped deterministic point IDs. This avoids one collection per workspace/generation. It depends on every write, scroll, count, validation, deletion, and query carrying a generation scope; tests must prove omission or mismatch is rejected in application code. Physical collection removal is allowed only when no generation of that contract is active, rollback-eligible, building, validating, or referenced by a job.

## Generation lifecycle

`ACTIVE` is derived from the workspace assignment pointer; it is not an independently writable state on a second record. This prevents a persisted `active` flag from disagreeing with the authoritative pointer.

| State | Meaning | Product reads | Writes | Activation/rollback/GC |
| --- | --- | --- | --- | --- |
| `planned` | Contract and capacity preflight recorded; no points created | No | No | May begin build; GC only after cancellation/audit |
| `building` | Baseline document versions and chunks are being indexed | No | Migration worker only | Cannot activate; resumable |
| `catching_up` | Baseline is complete; committed mutation events are replayed | No | Migration worker only | Cannot activate until caught up |
| `validating` | Candidate is frozen for consistency and smoke checks | No product reads; validation reads only | No writes except a controlled repair that returns it to `building` | Cannot activate until every gate passes |
| `ready` | Validation passed against a stated source-event cutoff | No | No; any later source event returns it to `catching_up` | May activate with explicit authorization |
| `active` (derived) | The assignment row points here | Yes | Active indexing path | Cannot be GC'd or overwritten |
| `superseded` | Former active generation; retained during rollback window | No normal product reads; rollback validation only | Mirror writes during retention | May be rollback target only while current; no GC before retirement |
| `failed` | Build or validation terminally failed after retry policy | No | Repair/retry creates a new attempt or returns to a safe build state | Never activate; GC only after audit and no references |
| `retired` | Explicitly removed from all assignment and rollback paths | No | No | GC eligible after reference scan and audit |

Transitions are monotonic except explicit retry from `failed` to a new build attempt. `ready` is invalidated by any newer document mutation not yet reflected in the candidate. An active generation is identified solely through the workspace assignment row; its visible lifecycle label is calculated when reading status.

## Proposed database design

This section proposes schema only. Do not add tables or migrations in this PR.

### Reuse existing entities

- `Workspace`, `Membership`, `KnowledgeBase`, `Document`, and `DocumentVersion` remain authoritative for tenant hierarchy and current source versions.
- `IndexJob` remains the worker execution record but should gain a stable operation/revision identity and optional generation target for retryable materialization. Redis carries wake-ups only; PostgreSQL is authoritative.
- Existing audit event storage records administrative lifecycle events with safe identifiers. Do not put document text or vectors in audit metadata.

### New concepts (minimum proposed set)

1. **`index_generations`** — one workspace-scoped candidate/retained generation. Columns: `id UUID PK`; `workspace_id FK`; `generation_number`; `profile_id`, `profile_version`; canonical `contract_json`; `contract_sha256`; `qdrant_collection`; `chunk_contract_json` or hash (if not already included in contract); `state`; `snapshot_event_id`; `last_reconciled_event_id` as informational only; `expected_document_count`, `indexed_document_count`, `expected_chunk_count`, `indexed_chunk_count`; `validation_report` containing safe counts/checks only; `created_by_user_id FK nullable`; `created_at`, `updated_at`, `ready_at`, `activated_at`, `retire_after`. Constraints: unique `(workspace_id, generation_number)`, unique `id` with `workspace_id` for composite references, foreign key to workspace, check constraints for state and positive counts, and at most one nonterminal candidate generation per workspace. The event ID is not a gapless replay cursor.
2. **`workspace_retrieval_assignments`** — exactly one row per workspace. Columns: `workspace_id PK/FK`; `active_generation_id UUID`; `assignment_epoch BIGINT NOT NULL`; `updated_at`; `updated_by_user_id`. Composite FK `(workspace_id, active_generation_id)` references a generation in the same workspace. Assignment epoch increments on activation and rollback and is used for compare-and-swap and observability.
3. **`document_index_events`** — durable transactional outbox for `upsert` and `delete` source mutations. Columns: `event_id BIGSERIAL PK`; organization/workspace/KB IDs; `document_id`; monotonic per-document `source_revision`; `operation`; `document_version` and `content_hash` for upserts; `created_at`; optional non-sensitive request/audit correlation ID. Do not FK `document_id` with `ON DELETE CASCADE`: the delete tombstone must survive the document row. Do not store content, vectors, credentials, or stored filesystem paths. Unique `(workspace_id, document_id, source_revision)`.
4. **`index_generation_items`** — resumable per-generation progress keyed by `(generation_id, document_id)`. Store source revision/version/hash, expected/indexed chunk counts, state, attempt count, lease expiry, safe error code, and timestamps. Keep the source identity/tombstone after source deletion; avoid a cascading FK to `documents`. A composite FK to generation is required.
5. **`index_generation_event_receipts`** — unique `(generation_id, event_id)` receipt with applied source revision/result. This records individual consumed events and avoids assuming that increasing sequence IDs commit in order or have no gaps. Retain events until all active migrations and rollback mirrors have receipts or an explicit snapshot compaction point.

Do not create a separate `RetrievalProfileAssignment` and `MigrationRun` if the assignment table and `IndexGeneration` already express those facts. Profile definitions can begin as a versioned code registry; the immutable serialized contract is persisted on the generation. Add a normalized profile table only if product-managed profile definitions become necessary. A later schema review must decide whether `Document.source_revision` is a new column or can be represented by an existing immutable version identity; it must be monotonic per document and change on delete tombstones.

## Full index build and concurrent document changes

The active MiniLM generation continues serving RAG throughout baseline indexing. The candidate is not visible to product requests.

### Change capture prerequisite

Every upload, replace, reindex-source change, move/scope change, and delete must write a `document_index_events` row in the same PostgreSQL transaction as the source mutation. Delete writes a tombstone with tenant scope and source revision before deleting or soft-deleting the source row. If the event cannot commit, the source mutation must not commit. Redis receives a wake-up after commit but is not the durable record. A reconciler polls unreceipted events and re-enqueues work after Redis loss/restart.

Use immutable `DocumentVersion` content as the source for upserts. For deletes, keep a tombstone event independent of a cascading document FK and defer file/vector cleanup while any build or rollback target can still need that source. The storage cleanup policy must become reference-aware.

### Snapshot barrier and baseline

1. Create a `planned` generation after verifying model artifacts, profile contract, storage preflight, supported document versions, and operator authorization.
2. Each source mutation takes a shared transaction-scoped per-workspace mutation-gate lock before changing documents and writing its outbox event.
3. At build start, briefly take the matching exclusive gate. It waits for earlier mutation transactions to commit, then records the maximum committed event ID as the baseline boundary. Release the gate immediately. This is a barrier, not a long-running snapshot lock.
4. Enumerate current non-deleted documents and their active, ready `DocumentVersion`; create durable generation items. Page by stable document ID. A source update during the scan creates an event after the boundary. The scan may observe either the pre-change or post-change version; replay always resolves the latest source revision and makes the candidate converge.
5. Read source files by immutable version, extract/reuse the same canonical text extraction, apply the exact recorded chunk contract, embed with the contract's model, validate all vectors, and idempotently upsert candidate points.
6. Replay all committed events after the boundary, recording per-event receipts. Do not advance a single numeric cursor past an event that might still be uncommitted. Per-document `source_revision` and latest-source resolution prevent old events from overwriting new content.

If an upload occurs halfway through the build, its row and outbox event commit together. It is either observed by the scan, replayed from the event, or both; idempotent identities make both safe. A replace creates a new immutable document version and newer source revision; the candidate eventually contains only the latest active version. A delete emits a tombstone; the candidate removes all that document's points in the generation even if the baseline scanner had already indexed it. A failed `IndexJob` leaves its item unacknowledged and candidate not ready; retry the same deterministic work or mark the generation failed. A worker restart recovers expired item leases and replays unreceipted outbox events. Resuming a migration reuses the same contract, generation UUID, point IDs, and durable receipts; it never starts the entire build from zero.

Event IDs are database sequence values and are not commit order. Replay must select visible committed events lacking a receipt, not use `event_id > last_seen` as a contiguous checkpoint. For concurrent changes to one document, acquire a row lock and increment `source_revision` in the source transaction. The consumer re-reads the latest committed source state before applying an event; a delete tombstone wins for a deleted revision. Replaying an older event after a newer one therefore cannot resurrect stale content.

### Idempotency and resume

- Generation item idempotency key: `(generation_id, document_id, source_revision, document_version, content_hash, chunk_contract_hash)`.
- Chunk identity: deterministic UUIDv5 of `contract_sha256`, `generation_id`, `workspace_id`, `document_id`, `document_version`, and `chunk_index`. Changing any part produces a different point identity.
- Upsert the entire document's candidate chunk set with stable point IDs. Record expected count and checksum before/after. On retry, Qdrant upsert replaces the same IDs. If chunk count shrinks, delete stale points for that same document/version/generation only after the new upsert succeeds.
- Write the DB receipt only after Qdrant acknowledges the upsert/delete. Crash after Qdrant succeeds but before receipt repeats an idempotent operation. Never mark the receipt first.
- A worker claims a generation item with a database lease and heartbeat, not a long-held DB transaction during embedding. Expired leases return to the retry queue. Use bounded attempts and backoff; permanent errors preserve safe error codes and block readiness.
- Reconciler compares planned generation items, source events, and receipts with Redis queue state and re-enqueues missing work after restarts. Database state, not process memory or Redis, determines progress.

## Validation gate

Model quality and migration integrity are separate gates. Public synthetic benchmark results justify evaluating a candidate; they do not prove private documents were indexed completely or correctly.

Before `ready`, validate all of the following for exactly one workspace and generation:

1. **Contract:** generation contract JSON hashes to the recorded SHA; the supported profile version maps to that exact model ID/revision, preprocessing, normalization, dimensions, distance, chunker, and payload schema. No unresolved/unknown fields.
2. **Model load:** exact pinned artifact is provisioned offline; expected model revision/weights are verified; `trust_remote_code=False`; no network fallback; smoke query/document vectors have correct dimensions, finite values, and expected norm.
3. **Qdrant collection:** exact contract collection exists, has exactly the expected dense vector name/configuration, dimension, cosine metric, and payload indexes. A mismatch blocks validation; never repair an existing collection by changing its dimension in place.
4. **Source coverage:** enumerate current non-deleted documents and the current active `DocumentVersion` at the final event cutoff. Every eligible source has exactly one complete generation item matching its current source revision and content hash. Missing sources, unsupported legacy rows without a recoverable version, stale versions, or extra deleted/inactive sources block readiness.
5. **Chunks/vectors:** recompute expected chunk counts under the pinned chunk contract; compare expected/indexed counts; verify unique deterministic chunk identities; verify point IDs and payload generation/contract/organization/workspace/KB/document/version/hash metadata. Reject duplicate logical chunk keys, wrong-generation payloads, non-finite vectors, and inconsistent dimensions. Qdrant collection count alone is insufficient.
6. **Tombstones/active versions:** deleted sources and non-active document versions return no points in the candidate scope. Current production active-version rules remain in force.
7. **Tenant metadata:** each point's organization/workspace/KB chain matches PostgreSQL. Candidate validation runs with tenant filters and cannot broaden the authorized Knowledge Base set.
8. **Caught-up state:** every committed source event up to a barrier-established cutoff is receipted, no generation item is leased/queued/failed, and no event remains in-flight for this generation. A newer event invalidates `ready` and returns it to `catching_up`.
9. **Retrieval smoke:** run a small deterministic set of safe queries within this workspace; verify the expected indexed source is returned, returned payloads carry the exact generation and tenant IDs, and an unauthorized KB/workspace probe returns no results. Do not persist question text or private snippets in the report.
10. **Operator review:** show migration counts, failures, capacity, benchmark caveats, and exact from/to profile/contract; a tenant administrator explicitly approves activation.

Validation report stores counts, hashes, timestamps, check version, and safe failure codes only. It stores no source text, vectors, query strings, or model paths. Benchmark quality validation remains an independent offline/research decision. No-answer/abstention behavior requires its own product evaluation and is not inferred from index completeness.

## Atomic activation and request-path binding

The database row in `workspace_retrieval_assignments` is the only active-generation authority. Do not use `.env`, service restart, mutable process globals, a Qdrant alias alone, or independent reads of profile settings in the embedding and retrieval layers.

An activation transaction:

1. Requires a current workspace-admin authorization, an expected old generation ID/assignment epoch, and a `ready` candidate belonging to that same workspace.
2. Takes a row lock on the workspace assignment and the short exclusive workspace write gate. The candidate replay catches up all committed events through a final barrier cutoff. If the delta cannot be completed within the configured short gate budget, release the gate without changing the pointer, continue replay, and retry later.
3. Re-runs the fast integrity checks under the gate: no pending event, candidate validation still current, target collection/config exists, no failed or in-flight items, and all source versions match the cutoff.
4. In one PostgreSQL transaction, compare-and-swap `active_generation_id` and `assignment_epoch`, write the activation audit event, set the candidate to ready-for-activation/active-by-pointer semantics, mark the prior generation superseded with `retire_after`, and increment the assignment epoch. Commit is the linearization point.
5. Releases the gate. Source writes resume and newly dispatched work resolves the now-current generation.

RAG request sequence:

```text
authenticate
  → authorize requested KBs in PostgreSQL
  → confirm one workspace
  → read assignment + immutable generation contract once
  → validate generation belongs to workspace and is active
  → load embedding implementation by exact contract ID
  → embed query and verify dimension/finite/norm
  → verify Qdrant collection contract
  → search exact collection with generation + tenant + KB filters
  → map hits to sources
```

The resolved value is carried through all stages. Never call `get_settings().embedding_model` later in the same request. If database assignment, profile registry, loaded model, vector dimension, distance metric, Qdrant collection, or point generation metadata disagree, fail closed with a safe 503 and alert. Do not retry a different profile or collection. The existing Organization/Workspace/KB authorization remains the prerequisite and source of tenant scope.

Because the transaction changes a single assignment row, requests that read before commit use the old tuple; requests that read after commit use the new tuple. In-flight requests retain their resolved immutable tuple. Retain old collection/generation and both model implementations long enough for in-flight requests and rollback. Multi-process APIs need no mutable in-memory invalidation for correctness: each request reads PostgreSQL. The assignment epoch is included in logs/metrics and may later support a cache; no cache is recommended in v1.

## Post-activation writes and rollback

During a seven-day minimum rollback window, the active generation receives all source changes and the immediately previous generation is kept current by mirrored indexing. The window ends only after at least seven days, zero mirror backlog, no failed mirror jobs, active-generation health, and explicit administrator retirement. Seven days is a proposed starting policy; operators may lengthen it after operational testing, not silently shorten it.

Each upload/replace/delete commits a source revision and outbox event first. The indexing dispatcher resolves the active assignment. It indexes the new active generation and, during the rollback window, the eligible previous generation. Mirroring is temporary, scoped to one previous generation, and separately observable. Do not permanently dual-index all supported profiles.

To close the race between model inference and cutover, the active-generation worker computes vectors without holding the workspace gate, then takes the shared write gate, re-reads the active assignment/epoch, verifies that the vectors match that contract, and holds the gate through the Qdrant upsert and durable receipt. If the epoch changed while it embedded, it discards those vectors and re-embeds for the current contract. Activation's exclusive gate waits for these short final-write sections. Candidate replay is coordinated separately and may apply the final queued candidate delta while activation holds the gate; it cannot serve product reads.

Deletion preserves the current fail-safe behavior: synchronously remove points from every product-readable generation (active and rollback target) before committing the hard delete and its tombstone event. If any required Qdrant delete fails, the API does not commit the source deletion and returns an error; repair reconciles any partially deleted generation from the still-present source row. Candidate-only generations are removed by the durable tombstone before they may validate or activate. A future soft-delete design may replace this ordering only if RAG requests also exclude deleted documents reliably while asynchronous vector cleanup runs.

If active indexing fails, preserve current document semantics and show queued/failed status; retry from durable state. If rollback mirror indexing fails while active succeeds, keep serving the active profile, mark rollback as temporarily unavailable/degraded, alert an administrator, and retry/replay the outbox. Do not advertise rollback as ready until the old generation catches up. A delete tombstone is applied to both generations before cleanup. A document version change indexes the latest version in both; old versions remain inactive and are removed from both only after successful replacement/deletion semantics.

Rollback is a pointer change back to the previous generation, not a full reindex. Preconditions: the target collection and exact model artifacts/config are available; its contract passes validation; mirror lag is zero and its event receipts cover the latest barrier; required active documents are covered; source tenant filters match; an authorized workspace admin supplies the expected current generation/epoch and reason. Under the same short exclusive write gate, catch up the final delta, verify, transactionally compare-and-swap the pointer, increment epoch, and write a rollback audit event. If the target is behind and cannot be caught up within the gate budget, do not switch; continue replay and retry later.

After rollback, the prior BGE generation becomes superseded and the restored MiniLM generation becomes active. Mirror the current generation as the new rollback target for a fresh bounded window if capacity and policy allow. Never delete or overwrite the target during rollback. If the previous generation has been retired, rollback is unavailable without a new migration; the UI and API must say so clearly.

Retirement is separate from activation/rollback. A generation is eligible only after the rollback window expires, it is not active or a rollback target, its migration and jobs are terminal, all source changes are reconciled, the replacement has passed health checks, the maximum RAG request lifetime/drain grace has elapsed (or distributed generation-read leases prove no request still uses it), and a workspace admin confirms. If read leases/worker state cannot be checked, garbage collection fails closed. Record an audit event. Delete only that generation's points using its exact generation filter. Delete the shared contract collection only when no generation across any workspace references it and policy allows; never remove a collection because one workspace generation is retired.

## Cache, restart, and multi-process behavior

V1 does not cache active assignment metadata. PostgreSQL is authoritative; cache absence or Redis unavailability cannot change the chosen embedding space. The extra small assignment read is preferred over a stale model/index race.

If a future measured need adds a cache, use key `retrieval-assignment:{workspace_id}:{assignment_epoch}`. Cache value includes active generation UUID, immutable contract hash, collection, and scope. Activation/rollback writes the database row first, then publishes the new epoch for invalidation. Reads must verify the epoch against PostgreSQL before use; if Redis or invalidation is unavailable, read PostgreSQL directly. A cached contract/collection mismatch fails closed. TTL bounds stale entries but is not a correctness mechanism.

After API restart, each request reloads the pointer and contract from PostgreSQL. After worker restart, generation items, source events, receipts, and leases recover from PostgreSQL; Redis queue entries are recreated by reconciliation. After full Compose restart, PostgreSQL assignment and progress plus durable Qdrant collections remain authoritative. A missing active collection makes RAG unavailable for that workspace and raises an alert; never fall back to another collection. A missing candidate collection fails/resumes the candidate build while the old active generation remains available. No authoritative migration state may exist only in a process or Redis.

Multiple API processes observe committed epochs through PostgreSQL. Each request captures one epoch and uses it end-to-end. A stale instance cannot combine a new model with an old collection because it does not reuse a process-global profile decision; it resolves a complete `ResolvedRetrievalIndex` per request and checks its contract. An activation does not mutate models inside an in-flight request. Model instances may be cached by immutable contract hash, never by display profile name alone.

## Security and tenant isolation

Authorization is resolved before profile assignment. The user must have access to every requested KB; all selected KBs must share one workspace; only then may the assignment for that workspace be read. Assignment resolution cannot add or widen KB scope.

Every point contains organization, workspace, KB, document, version, and generation IDs. Every search includes SQL-authorized organization/workspace/KB filters and the exact generation filter. Every mutation and cleanup is scoped to the same tenant IDs plus generation/document/version. A collection is not a security boundary; PostgreSQL authorization is. Avoid IDs, names, content, query text, vectors, token values, and filesystem paths in audit logs. Enforce route-level workspace-admin roles for migration controls; normal employees have none. Platform operators require an explicit audited tenant scope and do not get synthetic membership.

Shared contract collections have a larger blast radius if code omits filters. Mitigate with a typed resolved-index object, a single Qdrant adapter that constructs mandatory filters, no route-supplied collection names, strict metadata checks, query/scroll/delete tests for cross-tenant boundaries, and authorization tests proving inaccessible IDs are rejected before Qdrant is called.

## Failure-mode matrix

| Failure | Safe behavior |
| --- | --- |
| BGE artifact unavailable | Candidate cannot start/resume; current active MiniLM continues serving; no implicit download |
| BGE model load failure | Candidate item fails/retries within policy; do not alter active assignment or use another embedding model |
| Worker crashes mid-build | Lease expires; deterministic point upsert and receipt order permit retry; resume from persisted item/event state |
| Qdrant unavailable | Queue durable retry; do not mark item/receipt complete; active retrieval follows its existing availability behavior |
| PostgreSQL unavailable | Do not resolve an assignment from stale process memory; fail RAG closed and stop activation/source mutations |
| Partial document indexing | Item remains incomplete; generation cannot become ready; retry or report safe failure code |
| Dimension mismatch | Reject vectors before Qdrant write/search; fail candidate or request; never probe another collection |
| Wrong embedding-space identity | Contract hash/collection/model check fails closed and emits alert; no query sent |
| Candidate collection missing | Candidate build can recreate only its exact contract collection after checking no conflicting collection; active system unchanged |
| Candidate validation fails | Remain `validating` or mark `failed`; preserve report and active pointer; repair creates a new validation attempt |
| Activation transaction fails | Transaction rolls back pointer and audit together; old assignment remains authoritative; release gate and retry only after diagnosis |
| API process has stale cache | V1 has no assignment cache; if a future cache cannot verify epoch, bypass it or return unavailable |
| Rollback requested | Revalidate target and mirror watermark under barrier; refuse if stale, missing, or wrong contract; active pointer stays put |
| Disk capacity exhausted | Preflight blocks start; during build pause/retry and alert; do not delete old active/rollback data to make room |
| Model artifact missing after restart | Candidate or rollback target unavailable; active generation remains if its contract is still loaded; never substitute weights |
| Document deleted during build | Durable tombstone is replayed; generation item becomes deleted and its points are removed by exact generation filter |
| Redis loss/restart | Poll PostgreSQL outbox/jobs and republish wake-ups; no mutation is lost because Redis is not authoritative |
| Event delivery order/gaps | Per-event receipts plus source revisions and latest-state resolution; no numeric high-water cursor skips pending commits |
| Mirror backlog during rollback window | Continue active service; flag rollback degraded and retry; block rollback and old-generation retirement until caught up |

## Capacity and hardware acceptance

For each generation, calculate raw vector payload exactly as:

```text
raw_vector_bytes = vector_count × dimensions × 4
```

For BGE-M3 this is `vector_count × 4096` bytes for float32, before payload, HNSW/segments, WAL, replicas, filesystem, or backups. During migration, old and candidate storage coexist:

```text
peak_required_disk ≥ current_active_index_bytes
                    + candidate_index_estimate_bytes
                    + model_artifact_bytes
                    + measured temporary/WAL/backup overhead
                    + operator-configured free-space reserve
```

Memory preflight must also account for concurrent process residency during build and rollback mirroring:

```text
peak_host_memory ≥ API active-model resident memory
                   + worker candidate-model resident memory
                   + optional rollback-model resident memory
                   + Qdrant resident/working memory
                   + OS and configured process headroom
```

Measure these terms under the actual load. The benchmark's process RSS is not the size of the model weights and may not include all unified accelerator allocations. Limit concurrent migration/embedding workers per host to a measured safe value.

Do not extrapolate the benchmark's 44-vector Qdrant directory to enterprise corpora. Estimate with the target environment's representative document sizes, chunk count, payload fields, Qdrant version/configuration, replication/shard settings, and actual collection measurements. Include duplicate storage from rollback mirroring and ensure there is room for Qdrant optimization/WAL and normal operational growth. The migration preflight fails before work begins if free space plus approved capacity cannot satisfy the measured estimate and reserve. It must never reclaim the old active generation automatically.

The 2.27 GB safetensors artifact and 1077.9 MiB measured process RSS are observations from one Apple MPS run, not universal RAM/VRAM requirements. The 28.709 ms median includes one small workload and is not an SLO. No CPU/server/GPU sizing conclusion follows.

Before production pilot, benchmark the exact immutable contract on: Apple Silicon pilot, CPU-only enterprise server, and GPU-capable enterprise server where relevant. Measure model cold/warm load; per-batch and end-to-end document embedding throughput; query embedding p50/p95 under concurrency; full indexing time; memory/RSS and accelerator memory; disk before/during/after migration; Qdrant CPU, memory, latency, and disk; concurrent uploads/replacements/deletes; restart/resume time; and active plus mirrored write overhead. Use representative authorized corpora with documented retention and privacy controls. Define acceptance thresholds with product/operations before collecting results.

## Administrator UX and audit

The system page remains a read-only operational view until APIs and protections exist. When implemented, workspace admins see:

- active profile and generation (`Compact · Active`, or `Balanced Multilingual · Active`), profile version, contract revision identifier, last validation time, and capacity status;
- candidate state (`Preparing`, `Catching up`, `Validating`, `Ready`, `Failed`) with eligible document count, completed/failed counts, expected/indexed chunks, event lag, capacity estimate, last progress time, and safe error codes;
- separate actions: **Prepare profile**, **Review validation**, **Activate**, **Rollback**, **Retire old generation**.

Preparation requires a review page showing exact target profile/contract, expected workspace, document counts, added storage and compute, rollback capacity, and impact. Activation and rollback require an explicit confirmation dialog stating from/to generation, workspace, current validation/catch-up state, and rollback-window consequences; require typed confirmation or an equivalent unambiguous second step and a reason. Do not combine prepare, activate, and cleanup into one button. Employees see no migration control. Failed or stale validation disables activation.

Audit event types: `retrieval_migration_created`, `retrieval_migration_started`, `retrieval_index_item_failed`, `retrieval_migration_validation_passed`, `retrieval_migration_validation_failed`, `retrieval_profile_activated`, `retrieval_profile_rollback`, `retrieval_generation_retired`, and `retrieval_generation_deleted`. Record actor, workspace/org IDs, profile ID/version, contract hash, generation ID, assignment epoch, timestamp, outcome, safe counts, and correlation ID. Do not log content, raw questions, vectors, passwords, bearer tokens, private model paths, or raw exception text that may embed sensitive values.

## Future API proposal

Every endpoint checks authenticated membership and workspace scope. Mutations require a workspace `admin` membership in v1. Platform administrator support access is separate, explicitly scoped, and audited. Outputs omit document content, vectors, raw cache paths, token values, and unsafe exception details.

| Method and path | Role | Input | Safe output and main errors |
| --- | --- | --- | --- |
| `GET /workspaces/{workspace_id}/retrieval` | Member with workspace access | None | Active profile/generation, assignment epoch, contract summary, retention state; `403`, `404`, `503` on unresolved active contract |
| `GET /workspaces/{workspace_id}/index-generations/{generation_id}` | Member with workspace access | None | State, counts, event lag, last progress, safe failure code, validation summary; `403`, `404` |
| `POST /workspaces/{workspace_id}/index-generations` | Workspace admin | `target_profile_id`, idempotency key | Planned generation and capacity estimate; `409` unsupported/already-running, `422` failed preflight, `503` dependency unavailable |
| `POST /workspaces/{workspace_id}/index-generations/{id}/start` | Workspace admin | Idempotency key | Started/resumed status; `409` wrong state, `422` invalid contract, `507` insufficient capacity |
| `POST /workspaces/{workspace_id}/index-generations/{id}/validate` | Workspace admin | Requested validation version | Validation counts/status; `409` events pending, `422` integrity failures, `503` dependencies unavailable |
| `POST /workspaces/{workspace_id}/retrieval/activate` | Workspace admin | Target ID, expected active ID/epoch, reason, one-time confirmation | New generation/epoch; `409` assignment changed or candidate stale, `422` not ready, `423` write gate timed out |
| `POST /workspaces/{workspace_id}/retrieval/rollback` | Workspace admin | Target ID, expected active ID/epoch, reason, confirmation | New generation/epoch; `409` stale mirror/epoch, `422` target invalid, `423` barrier timeout |
| `POST /workspaces/{workspace_id}/index-generations/{id}/retire` | Workspace admin | Reason, confirmation | Retirement scheduled/completed; `409` active/rollback/job/request references remain |

Do not expose a generic endpoint that accepts arbitrary model IDs, revisions, collection names, or dimensions. The profile registry allowlists immutable contracts.

## Request-path and cache tests required before implementation

The RAG API first authorizes selected Knowledge Bases using the current enterprise authorization helpers, verifies they share a workspace, and resolves the assignment once. The request keeps the resolved generation object immutable. A request cannot accept an index generation from the caller. Before embedding/search, check exact contract fingerprint, model revision, dimensions, pre/postprocessing, collection vector size, metric, workspace assignment epoch, generation ID, and tenant scope. If a BGE/1024 query meets a MiniLM/384 contract/collection, the adapter must throw before the Qdrant search method is invoked; reciprocal test for MiniLM→BGE is required.

## Test and acceptance strategy

Tests are a future implementation requirement, not run or added in this documentation milestone.

- **Unit:** canonical profile contract hashes; immutable serialization; collection-name validation; deterministic document/chunk point IDs; vector finite/dimension/norm guards; lifecycle transition table; generation-scoped Qdrant filters; state/output redaction.
- **Explicit wrong-space guards:** BGE query can never be sent to MiniLM collection and MiniLM query can never be sent to BGE collection. Test with equal-dimension fake profiles too, proving ID/hash rather than dimension is decisive.
- **Database integration:** unique one-active assignment semantics; same-workspace composite FK; source mutation and outbox atomicity; delete tombstone surviving row deletion; role checks; event receipt uniqueness; migration item persistence across source deletion.
- **Worker/Qdrant integration:** generation-local deterministic upserts, duplicate retry, stale chunk removal, filter-scoped delete, contract/vector config mismatch refusal, tenant and KB isolation, excluded inactive/deleted versions, exact active-version coverage.
- **Migration interruption:** crash before Qdrant upsert, after upsert before receipt, after receipt, during event replay, during validation, during activation transaction, and after activation before queue acknowledgement; each resumes or leaves old pointer usable.
- **Concurrent upload/update/delete:** perform each at snapshot start, mid-scan, replay, validation, and cutover; prove no lost update, no resurrection, and no cross-tenant point.
- **Atomic cutover:** concurrent RAG requests observe wholly old or wholly new tuple. Inject activation failure and prove DB pointer/audit transaction rolls back; no mixed model/collection calls.
- **Rollback:** current target catches up within window; mirror failure blocks rollback; rollback CAS conflict refuses; restore pointer preserves post-activation writes; no full-corpus reindex is needed.
- **Restart and multiprocess:** restart API, worker, Redis, Qdrant, and whole Compose at each lifecycle stage; multiple API processes cache model objects but always resolve the same committed epoch and contract; no stale pointer use.
- **Capacity preflight:** expected vector counts, model artifact, temporary/rollback usage, measured overhead, reserve threshold, insufficient space, missing weights, and restart with unavailable artifact.
- **Authorization/UI:** user and unauthorized org/workspace roles cannot list, prepare, validate, activate, rollback, or retire; workspace admin cannot affect another workspace; progress is tenant-scoped; employee UI contains no migration controls; typed confirmation includes the actual scope.
- **Live acceptance:** isolated pilot workspace, known active generation, synthetic or explicitly approved documents, baseline traffic continuity, event catch-up, validation, activation, rollback, audit, and retirement. No production/customer document is used without explicit data approval.

## Rollout phases

Each phase is independently reviewable; production activation is a later operator decision.

1. **Contracts and threat model:** immutable profile registry/contract hashing, typed resolved-index object, API authorization plan, SLO/capacity policy; no production selector.
2. **Generation schema and source outbox:** Alembic tables, source-revision invariants, transactional upload/replace/delete events, migration barrier; old runtime continues using current index.
3. **Generation-aware Qdrant adapter:** contract collections, generation/tenant filters, deterministic point identity, no writes from RAG routes; wrong-space tests.
4. **Resumable candidate worker:** generation items, event receipts, lease recovery, reconciliation, metrics; build only in a disposable/local test workspace first.
5. **Completeness validation:** DB/Qdrant reconciliation, safe random retrieval probes, failure handling; candidate still not readable by product traffic.
6. **Atomic assignment and rollback mechanics:** compare-and-swap pointer, write gate, bounded mirrored writes, rollback and retention; integration/multiprocess tests.
7. **Admin controls and audit UX:** workspace-admin-only prepare/status/validate/activate/rollback/retire with explicit confirmation.
8. **Isolated pilot acceptance:** hardware and representative corpus measurements, rollback rehearsal, security review, operator sign-off. Only a separate explicit release/activation decision can enable production.

The first implementation should not begin with the UI. Establish and prove immutable contracts, outbox correctness, data isolation, and generation-aware worker semantics first.

## Benchmark-run provenance improvement (design only)

Future aggregate reports can include a random benchmark run UUID; commit SHA; model ID/revision; process-run UUID and process start/end timestamps; OS family/version; architecture; software versions; selected accelerator class/slot (for example `mps:0`, without hardware serial); corpus fingerprints; and a boolean indicating that the harness launched a fresh process. Do not record hostname, username, home directory, MAC address, serial numbers, raw paths, private text, or vectors. A random host-session fingerprint may group runs within one explicitly launched experiment but must rotate and must not be derived from stable personal-machine identifiers. The current benchmark outputs do not independently attest same-host/fresh-process facts; preserve that limitation in future comparisons.

## Open questions before implementation

1. What is the expected maximum number of workspaces per deployment, and should the shared-per-contract collection strategy later use Qdrant tenant shard keys?
2. What exact rollback window and temporary free-space reserve are acceptable for local/on-prem installs with differing disks?
3. Which legacy documents lack immutable stored `DocumentVersion` source files, and should preflight block or offer a separately authorized source recovery step?
4. Does current storage retain prior document version files long enough for migration/resume, and what retention policy is safe for deletion tombstones?
5. What per-workspace change rate and cutover gate duration are acceptable? If the final delta cannot catch up within the gate budget, activation must defer.
6. Should a workspace admin require organization-admin approval for a resource-intensive profile change? Define this before API/UX implementation.
7. Which production hardware/corpus thresholds qualify Balanced Multilingual for a pilot, given that the public benchmark alone is not customer evidence?
8. Should platform support staff have an audited break-glass capability, or should only tenant admins control assignment in v1?

## Explicit answers

1. **How do we guarantee MiniLM and BGE-M3 vectors can never be mixed?** Give each immutable contract a different contract hash and Qdrant collection; bind query model, dimensions, metric, generation, and collection in one resolved request object; verify all metadata and dimensions before any Qdrant call; filter the exact generation. A mismatch fails before search. Tests cover both cross-pairings.
2. **Where should assignment live in v1?** Workspace. It matches multi-KB RAG scope and permits one bounded enterprise pilot without a tenant-wide or global switch.
3. **Can BGE-M3 be indexed while MiniLM continues serving traffic?** Yes. Build and validate a non-readable generation in BGE-M3's distinct contract collection while the workspace pointer still targets MiniLM.
4. **How are document changes captured during migration?** Source mutation plus durable outbox event in one PostgreSQL transaction; high-water barrier, event replay, per-document revision, and tombstones converge candidate to latest source state.
5. **How does interrupted migration resume?** Reuse durable generation/item state, leases, per-event receipts, immutable source-version identity, and deterministic upsert/delete IDs; reconcile PostgreSQL work to Redis. Never restart full corpus solely due worker crash.
6. **What must pass before activation?** Exact contract/model/Qdrant metadata; all current active document versions and chunks covered; no missing/extra/deleted/inactive points; correct tenant/KB/generation payloads; all outbox events through final barrier receipted; zero failed/leased items; smoke retrieval and isolation probes; capacity and administrator review.
7. **How is activation atomic?** Resolve in-flight RAG to a single immutable snapshot. Under short workspace write gate, catch up candidate and compare-and-swap one PostgreSQL assignment row plus audit in a transaction. Commit is cutover; earlier requests finish old, later requests resolve new.
8. **Can rollback occur without full reindex?** Yes, while the previous generation is retained and kept current; rollback revalidates it and switches the same pointer back.
9. **How are writes handled during rollback window?** Durable source events are indexed to the active generation and mirrored to one prior rollback generation for a proposed minimum seven days. Mirror lag blocks rollback/retirement, not active service; this bounded dual-index period ends after zero lag and explicit retirement.
10. **When may old MiniLM index be deleted?** After minimum retention expires, replacement is healthy, mirror is caught up, no assignment/job/request references remain, admin explicitly retires it, and an audit event is recorded. Shared contract collection is deleted only when no generation references it.
11. **How is tenant isolation preserved?** Keep current PostgreSQL authorization hierarchy and KB scope resolution; include mandatory org/workspace/KB/generation filters in all vector reads/writes/deletes; never treat collection separation as authorization.
12. **How do multiprocess APIs observe activation?** Each request reads committed assignment/epoch from PostgreSQL and carries the resolved immutable tuple throughout. V1 does not cache assignment state; model cache keys use contract hash only.
13. **What capacity preflight is required?** Estimate vectors × dimensions × 4, measure Qdrant payload/index overhead on representative data, add both active and candidate indexes, model files, WAL/temporary/replica overhead, and operator reserve. Block before building if capacity is inadequate; never evict active rollback data automatically.
14. **What is the safest implementation order?** Contracts and threat model; outbox/schema; generation-aware Qdrant adapter and wrong-space tests; resumable candidate worker; integrity validation; atomic assignment/rollback; admin UX/audit; isolated hardware and corpus pilot.
15. **What remains unimplemented after this PR?** All runtime and data-plane work: schemas/migrations, outbox/tombstones, profile assignment, new production collections, model loader, migration/resume workers, activation/rollback APIs, dual-indexing, cache, admin controls, live reindex, and BGE-M3 activation.

## Related documents

- [Retrieval profile benchmark roadmap](../roadmap/retrieval-profile-embedding-benchmark.md)
- [BGE-M3 dense-only benchmark](../../evaluation/experiments/compact-multilingual-bge-m3-v1.md)
- [E5-base benchmark](../../evaluation/experiments/compact-multilingual-e5-base-v1.md)
