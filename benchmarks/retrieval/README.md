# Retrieval Quality Benchmark v1

This is evaluation-only tooling. It measures labeled document/chunk retrieval over synthetic fixtures; it does not call generation, change production retrieval, use tenant documents, or evaluate production answer quality. The committed corpus is a **fixture / engineering validation corpus**, not an authoritative enterprise benchmark. Real-world retrieval quality remains **NOT YET ESTABLISHED**.

## Architecture and safety

- Document chunking uses `app.services.rag.chunker.chunk_text` with explicit, reported size/overlap.
- Real model inference goes through the production `EmbeddingService` semantics: asynchronous batched encoding with `normalize_embeddings=True` and NumPy vectors. The selected benchmark model is instantiated offline and is never written to application settings.
- Real-model runs use CPU as the common inference device, so future model comparisons made with this runner use a consistent device.
- Search uses Qdrant's cosine metric, normalized vectors, score ordering, and `limit` search behavior. The isolated runner uses `QdrantClient(":memory:")`; it has no network endpoint and cannot reach the Docker Compose production Qdrant service. It creates a unique `modai_benchmark_<run-id>` collection and deletes only the collection lease it created.
- The runner does not import application routes, database models, Alembic, or generation services. No database or production collection is used.
- CLI model snapshots are cache-only. Hugging Face/Transformers offline mode is enabled before model loading. There is no model-download fallback.
- The `--dry-run` stub validates the entire pipeline with deterministic hash vectors. Those metrics are plumbing checks, not embedding-model quality results.

Production currently uses `rag_documents`, cosine distance, normalized SentenceTransformer vectors, `chunk_text` (700 words / 100 overlap), and RAG top-k 3. The benchmark defaults to the configured chunk size/overlap but requests at least five chunks so it can report Recall@1/3/5. It does not read `RAG_TOP_K` to change production behavior.

## Dataset schema

`datasets/v1/fixture.json` is versioned JSON with stable `document_id`, `query_id`, and optional `document_id::chunk-NNNN` labels. Language (`tr`, `en`, `mixed`) is independent of one or more retrieval categories (`single_document_fact`, `multi_document`, `long_document`, `semantic_distractors`, `unanswerable`). Validation rejects duplicate IDs, unknown references, blank questions, missing relevance on answerable cases, or relevance labels on unanswerable cases. `classification: "authoritative"` is an operator assertion, not an automated quality finding; the CLI also requires `--confirm-authoritative-corpus`. Only use it for a separately human-labeled, representative enterprise corpus. Keep private corpora and their outputs outside Git.

The fixture covers Turkish, English, mixed-language, single/multi-document, a long-tail chunk, a semantic distractor, and unanswerable questions. It contains only fictional text. Category groups intentionally overlap when a query has multiple categories; global metrics count each query once.

## Metrics

- **Recall@K:** macro-average across answerable queries of labeled relevant documents represented by the first K Qdrant chunk results, divided by all labeled relevant documents for that query. A document appearing in multiple chunks counts once.
- **Hit@K / source hit rate:** fraction of answerable queries with at least one relevant document represented by the first K Qdrant chunk results.
- **MRR@K:** mean reciprocal rank of the first relevant document in the deduplicated first-seen source order represented by the first K chunks; misses score zero.
- **Source precision@K:** relevant distinct documents represented by the first K chunks divided by all distinct documents represented by those chunks across answerable queries.
- **Chunk recall@K:** reported only for cases with explicit chunk labels.
- **Unanswerable behavior:** candidate-return rate and mean top cosine score. Vector search may return neighbors; this is not no-answer detection or answerability classification.
- Embedding and retrieval latency are medians from the current machine/run and are observational, not deterministic quality metrics.

Reports include only aggregate metrics and stable fixture IDs; they omit questions, source text, prompts, answers, user identifiers, credentials, and local model paths. Outputs go under ignored `artifacts/` unless a different local path is supplied.

## Provenance

Report schema 2 records benchmark source provenance as `source_sha` plus `source_sha_origin` (schema 1 had a single `git_sha` field):

- `explicit`: the operator passed `--source-sha` (exactly 40 hex characters, normalized to lowercase). It takes precedence over git discovery and is an operator assertion that the benchmark source matches that commit.
- `git`: `git rev-parse HEAD` succeeded in the repository containing the benchmark source. This identifies HEAD only, not uncommitted changes.
- `unavailable`: neither was available; `source_sha` is `null`.

Isolated container runs have no git tooling or `.git` metadata (and `.git` should not be mounted), so pass the SHA from the host, for example `--source-sha "$(git rev-parse HEAD)"`. `runtime_build_sha` separately records the dependency image's `BUILD_SHA` when it is a full SHA. It describes the deployed runtime image, which may intentionally differ from the benchmark source, and is never used as a substitute for `source_sha`.

## Run

Framework/dataset/metrics/reporting dry-run (no model download):

```bash
python -m benchmarks.retrieval.run \
  --dry-run \
  --dataset benchmarks/retrieval/datasets/v1/fixture.json \
  --chunk-size 700 --chunk-overlap 100 --top-k 5 \
  --output artifacts/retrieval-benchmark/v1/dry-run
```

The real MiniLM fixture command is offline and requires the exact pinned snapshot to already be fully cached:

```bash
python -m benchmarks.retrieval.run \
  --embedding-model sentence-transformers/all-MiniLM-L6-v2 \
  --revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 \
  --dataset benchmarks/retrieval/datasets/v1/fixture.json \
  --chunk-size 700 --chunk-overlap 100 --top-k 5 \
  --output artifacts/retrieval-benchmark/v1/minilm
```

Future isolated multilingual E5 experiment (same fixture; does not alter production configuration):

```bash
python -m benchmarks.retrieval.run \
  --embedding-model intfloat/multilingual-e5-small \
  --revision 614241f622f53c4eeff9890bdc4f31cfecc418b3 \
  --dataset benchmarks/retrieval/datasets/v1/fixture.json \
  --output artifacts/retrieval-benchmark/v1/e5-small
```

The pinned E5 profile applies its registered `query: ` / `passage: ` prefixes. Unknown models require an explicit pinned `--revision`; optional model-specific prefixes can be supplied with `--query-prefix` and `--passage-prefix`. Only pre-provisioned local weights are accepted. Do not put production documents in this fixture or commit model weights/results containing private data.

The CLI intentionally has no remote `--qdrant-url` option. A requested network endpoint is not supported; the in-memory backend and collection ownership guards are part of the safety boundary.

## Dataset schema v2 (labels only; not yet executable by the runner)

`schema_version: 2` datasets describe authoritative-evaluation labels. They are validated by `load_dataset_v2` / `load_any_dataset` (explicit version dispatch) and `python -m benchmarks.retrieval.validate <dataset.json>`. The benchmark runner still accepts only schema v1: `load_dataset` rejects v2 files before parsing and `RunConfiguration` rejects non-v1 dataset objects. Runner and metric support is deferred to P1-B. The v1 schema, the eight-query fixture and its fingerprint, and report schema 2 are unchanged.

- **Required source groups:** a query is complete only when every group is satisfied (AND across groups); a group is satisfied by any one member (OR within a group), for example equivalent TR/EN translations.
- **Label states are distinct:** `grade 2` (directly answers; must belong to a required group), `grade 1` (supporting or partial; never a group member), `grade 0` (judged irrelevant; only with `basis` `human_review` or `fixture_authored`), *unjudged* (no judgment for the query/document pair; never to be counted as 0), and *historical relationships* (legacy confusable references preserved as metadata, carrying no grade).
- **Evidence spans** are zero-based, end-exclusive Unicode code-point offsets into the exact stored `text`, with a SHA-256 of the UTF-8 span text. Text must already be NFC with `\n` line endings; the validator rejects other representations and never normalizes. `provenance.extraction.text_transform` (`none`, `nfc`, `lf_nfc`) records how labeled text was derived from extracted text, and `raw_text_sha256` identifies the raw extraction.
- **Lanes:** `real_representative` contains only `public_real`/`internal_approved` documents with complete provenance, human-reviewed labels and character spans; `synthetic_stress` holds synthetic and adapted legacy material; `fixture` is committable, synthetic and public. There is no `authoritative` value: `assess_dataset` reports review, provenance and attestation facts and always returns `real_world_benchmark_status: NOT YET ESTABLISHED`. Representativeness is an attestation bound to the corpus fingerprint, not a flag.
- **Families and versions:** `source_family_id`, `translation_group_id`, `variant_key`, `status`/`supersedes` and `temporal_intent` validate current-versus-obsolete and near-duplicate labels and give a future splitter the grouping needed to keep translations, versions and paraphrases (shared `scenario_id`) on one side of a DEV/TEST split.
- **Fingerprints** (`dataset_fingerprints_v2`) are order-independent and separate the corpus text, document metadata, query text, annotations and review state; model and run settings never enter them. Reports must not include per-document or per-span digests of private corpora.

`datasets/v2/example.json` is a fictional fixture for schema validation only. `adapters.adapt_legacy_corpus` converts `compact-multilingual-v1` and `cross-language-mirror-v1` in memory after verifying their pinned fingerprints and counts. Expected sources become single-member groups (`basis: legacy_expected_source`); all 492 and 40 confusable references stay unjudged historical relationships; facts, KB scope, `top_k` and categories are reported as limitations, and no evidence spans or translation equivalences are inferred. Adapted datasets are `synthetic_stress` and never authoritative. Private real corpora must stay outside Git.
