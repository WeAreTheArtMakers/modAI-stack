# Retrieval profile embedding benchmark roadmap

## Purpose

Evaluate whether a multilingual embedding profile materially improves retrieval over the current production baseline. This roadmap tracks benchmark evidence and a possible later controlled migration; it does not authorize a production profile change.

## Canonical benchmark corpus

Use the versioned, deterministic, fictional corpus `compact-multilingual-v1` for embedding comparisons. Its fingerprint is `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b`; it contains 44 documents and 156 cases: 132 answerable and 24 no-answer. The answerable split is balanced at 66 English and 66 Turkish queries, including 22 Turkish-query → English-source and 22 English-query → Turkish-source cases.

This is the canonical reproducible benchmark. The former private 92-case robustness corpus is not a repository dependency or canonical comparison set. Keep corpus inputs fictional and safe for repository use; never commit private company data, local caches, or model weights.

## Living milestone status

### Completed

- MiniLM production baseline architecture is in place and remains the active production profile.
- Production retrieval and embedding comparisons use fixed `RAG_TOP_K=3` / `K=3`.
- Retrieval Profile abstraction is implemented; profile switching remains disabled.
- `compact-multilingual-v1` is reproducible and committed with its fingerprint and manifest.
- MiniLM was rerun alongside the pinned E5-small candidate in an offline paired experiment.
- E5-small improved overall, English, and Turkish answerable retrieval on this corpus, and improved English-query → Turkish-source retrieval. It did not improve Turkish-query → English-source retrieval (still 0/22); no-answer confusability and hard-negative confusable-source frequency increased. See the complete measured comparison in [`compact-multilingual-e5-paired-v1.md`](../../evaluation/experiments/compact-multilingual-e5-paired-v1.md).
- Deep-rank and mirrored-set diagnostics are recorded in [`cross-language-diagnostics-v1.md`](../../evaluation/experiments/cross-language-diagnostics-v1.md). The canonical corpus has uneven directional query templates/lengths, but the separate 20-fact mirror also shows E5-small's TR-query → EN-source deficit. On canonical E5-small cases, only 7/22 expected sources rank within top 10 and 15/22 are below the top-20 window or absent. No prefix, truncation, normalization, or indexing bug was found.
- E5-small is **not a validated Compact Multilingual candidate**: aggregate and EN→TR gains are promising, but the persistent TR→EN retrieval weakness and increased no-answer confusability do not clear the product gate.
- The pinned E5-base snapshot was verified offline and benchmarked alongside fresh MiniLM and E5-small runs on the **same MPS device**. E5-base increased canonical TR→EN Hit@3 from 0 to 0.3182 and Recall@10 from E5-small's 0.3182 to 0.5909, but the matched mirror still has a 0.35 K=3 directional gap (TR→EN 0.55 versus EN→TR 0.90), and no-answer confusability rose to 20/24 cases. The measured comparison and resource costs are in [`compact-multilingual-e5-base-v1.md`](../../evaluation/experiments/compact-multilingual-e5-base-v1.md).
- E5-base is **not a validated Compact Multilingual candidate**: it improves coverage but leaves a material Turkish-query → English-source weakness and worsens confusable retrieval. No production profile change follows from this benchmark.
- The pinned `BAAI/bge-m3` dense-only candidate was provisioned deliberately and freshly compared with MiniLM, E5-small, and E5-base on common MPS. It achieved 130/132 overall Hit@3, 21/22 canonical TR→EN Hit@3 (22/22 Recall@5 and Recall@20), 22/22 EN→TR Hit@3, and a zero matched-mirror K=3 direction gap. Its 2.271 GB artifact, 1024-dimensional vectors, 28.709 ms median total retrieval, 1077.9 MiB (approximately 1.053 GiB) process peak RSS, increased hard-negative confusable retrieval, and mixed no-answer confusability do not support the “Compact” label. See [`compact-multilingual-bge-m3-v1.md`](../../evaluation/experiments/compact-multilingual-bge-m3-v1.md).
- BGE-M3 dense is **not activated**. The evidence maps to product-gate category B: strong retrieval quality with a higher resource profile; consider Balanced Multilingual, subject to a controlled design review.

### Current / next

- Next milestone: conduct a controlled **Balanced Multilingual profile migration/index-activation design review** using the BGE-M3 quality/resource evidence. This milestone is design-only; it does not activate a profile or authorize reindexing. Do not automatically begin implementation.
- Keep BGE-M3, E5-small, and E5-base experimental, inactive, and non-selectable. Do not change production `EMBEDDING_MODEL` or `RAG_TOP_K=3` based on this benchmark.

### If a future candidate passes review

- Validate the candidate-to-profile mapping.
- Design a controlled profile migration with an isolated new vector index, full document reindex, validation, atomic profile/index activation, and rollback capability.
- Keep the candidate inactive and non-selectable until the migration is implemented and explicitly approved.

### Later

- Evaluate no-answer and abstention quality as a separate capability; do not infer abstention from similarity alone or introduce a threshold from the current scores.
- Consider a bounded reranker if future evidence shows a material top-K ranking shortfall despite relevant sources appearing in a wider candidate pool. The current BGE-M3 run has 22/22 canonical TR→EN Recall@5 but 21/22 Hit@3, so reranking remains technically possible; its incremental benefit and cost were not measured and it is not the next milestone.
- Consider dense+sparse/hybrid retrieval only if measured results justify it.

## Benchmark principles

- Pin exact model revisions and record model identity, revision, license, artifact provenance, preprocessing, and corpus fingerprint.
- Provision model artifacts outside Git and run inference fully offline after provisioning.
- Compare models with the same corpus, documents, chunking, cases, fixed `K=3`, and Qdrant configuration; isolate their vector collections and verify vector-space identity before retrieval. Equal dimensions do not make different embedding spaces compatible.
- Apply each model's documented preprocessing consistently. Report English, Turkish, and both cross-language directions separately so an overall average cannot hide a language regression.
- Report retrieval quality alongside latency, memory, indexing cost, and storage; do not infer answer quality from retrieval metrics alone or fabricate unavailable measurements.
- Keep production on its current embedding model and `RAG_TOP_K=3`. Do not activate a candidate, switch profiles, enable a reranker/hybrid path, or reindex real user documents based only on a benchmark.
- Any eventual embedding-space change requires a controlled full reindex and a consistent, atomic index/profile activation with a rollback path. Never change only `EMBEDDING_MODEL` while serving vectors from another model.
