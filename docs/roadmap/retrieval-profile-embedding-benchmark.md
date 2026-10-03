# Retrieval profile embedding benchmark roadmap

## Purpose

Evaluate whether a multilingual embedding profile materially improves retrieval over the current production baseline. This roadmap tracks the benchmark and any later controlled migration; it does not authorize a production profile change.

## Canonical benchmark corpus

Use the versioned, deterministic, fictional corpus `compact-multilingual-v1` for embedding comparisons. Its expected fingerprint is `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b` and it contains 44 documents and 156 cases: 132 answerable and 24 no-answer. The answerable split is balanced at 66 English and 66 Turkish queries, including 22 Turkish-query → English-source cases and 22 English-query → Turkish-source cases.

This is the canonical reproducible benchmark. The former private 92-case robustness corpus is not a repository dependency and must not be used as the canonical future comparison set. Keep all benchmark inputs and outputs fictional and safe for repository use; never commit private company data, local caches, or model weights.

## Living milestone status

### Completed

- MiniLM production baseline architecture is in place.
- Production retrieval uses fixed `RAG_TOP_K=3`; benchmark comparisons also use fixed `K=3`.
- Retrieval Profile product abstraction is implemented, with profile switching disabled.
- `compact-multilingual-v1` is reproducible and committed with its fingerprint and manifest.
- A MiniLM baseline has been run on this canonical corpus. Its results are useful context, not a substitute for rerunning MiniLM alongside a candidate in a paired experiment.

### Current

- Provision the exact pinned `intfloat/multilingual-e5-small` snapshot outside Git.
- Once provisioned and verified, run a paired, offline MiniLM vs E5-small benchmark on `compact-multilingual-v1` using the same documents, cases, chunking, Qdrant configuration, and fixed `K=3`, with isolated vector collections.

### Next if E5 passes review

- Validate the Compact Multilingual candidate-to-profile mapping.
- Design a controlled profile migration with an isolated new vector index, complete reindex, atomic profile/index activation, and rollback capability.
- Keep the candidate non-selectable and inactive until the migration is implemented and explicitly approved.

### Next if E5 fails review

- Evaluate `intfloat/multilingual-e5-base` as the next multilingual candidate.
- Consider `BAAI/bge-m3` only if the evidence justifies its additional footprint and complexity.

### Later

- Evaluate no-answer and abstention quality.
- Evaluate a reranker.
- Consider dense+sparse/hybrid retrieval only if measured results justify it.

## Benchmark principles

- Pin exact model revisions and record model identity, revision, license, artifact provenance, preprocessing, and corpus fingerprint.
- Provision model artifacts outside Git and run inference fully offline after provisioning.
- Compare models with the same corpus, chunking, cases, fixed `K=3`, and Qdrant configuration; isolate their vector collections and verify vector-space identity before retrieval. Equal dimensions do not make different embedding spaces compatible.
- Apply each model's documented preprocessing consistently. Report English, Turkish, and both cross-language directions separately so an overall average cannot hide a language regression.
- Report retrieval quality alongside latency, memory, indexing cost, and storage; do not infer answer quality from retrieval metrics alone or fabricate unavailable measurements.
- Keep production on its current embedding model and `RAG_TOP_K=3`. Do not activate a candidate, switch profiles, or reindex real user documents based only on a benchmark.
- Any eventual embedding-space change requires a controlled full reindex and a consistent, atomic index/profile activation with a rollback path. Never change only `EMBEDDING_MODEL` while serving vectors from another model.
