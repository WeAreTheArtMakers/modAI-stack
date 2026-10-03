# Retrieval profile embedding benchmark — next experiment

## Goal

Determine whether a multilingual embedding profile materially improves retrieval over the current production baseline. This is a planned experiment only: do not download candidate models or change production configuration as part of product-profile presentation work.

## Candidate sequence

1. Baseline: `sentence-transformers/all-MiniLM-L6-v2`.
2. First candidate: `intfloat/multilingual-e5-small`.
3. Later, only if local resources and network policy permit: `intfloat/multilingual-e5-base` and `BAAI/bge-m3`.

Pin exact model revisions and licenses, provision weights outside Git, and run fully offline after provisioning. Do not expose a candidate as an active production profile until the measurements and reindex implications are reviewed.

## Evaluation design

Use the same private 92-case robustness corpus and its existing fingerprint, with identical documents, splits, Qdrant settings, chunking, and fixed `K=3`. Keep raw questions, documents, per-case outputs, and model caches outside the repository. Do not tune thresholds on the holdout set.

Report, per model:

- overall Hit@3, MRR, source accuracy, and fact coverage;
- English and Turkish Hit@3 separately;
- cross-language retrieval: Turkish query → English document and English query → Turkish document;
- embedding latency, peak RAM, vector dimension, and Qdrant storage/index impact;
- whether results are comparable under each model's required query/document prompting or normalization.

Include confidence/context for this small synthetic corpus and do not infer answer quality from retrieval metrics alone. A language-specific regression must remain visible rather than being hidden by a global average.

## Productization gate

The profile catalog remains read-only until a candidate has been benchmarked and selected. Switching profiles must be an explicit, controlled migration: embedding spaces and dimensions are not interchangeable, so existing vectors must be rebuilt and activated consistently before the new profile serves queries. Never change only `EMBEDDING_MODEL` while retaining vectors from another model.
