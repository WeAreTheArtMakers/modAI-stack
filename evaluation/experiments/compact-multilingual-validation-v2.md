# Compact Multilingual embedding validation v2

## Decision

**E5 validation is blocked by model provisioning. No production reranker/embedding recommendation can be made for E5, and no E5 quality or resource result is reported.** The full paired K=3 benchmark could not run because the pinned `intfloat/multilingual-e5-small` safetensors snapshot was not completely provisioned. Keep Compact Multilingual experimental. Production remains on `sentence-transformers/all-MiniLM-L6-v2`, with `RAG_TOP_K=3`; no profile switching, production reindex, production Qdrant access, or generation-model change occurred.

The MiniLM figures below are a completed baseline on the newly versioned synthetic corpus. They do not predict E5 behavior or customer workload quality.

## Reproducible corpus

- Version: `compact-multilingual-v1`
- Canonical corpus fingerprint (version + ordered documents + validated dataset): `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b`
- Evaluation dataset fingerprint: `12fb1371a48a5b4b019f75e5bb423ebbfe2ac0d257d214c38581e6c8f540ee49`
- 44 fictional documents; 156 cases total: 132 answerable and 24 no-answer/insufficient-evidence.
- Answerable queries are balanced: 66 English, 66 Turkish. No-answer queries: 12 English, 12 Turkish.
- Case types: 88 normal, 44 hard-negative, 24 no-answer.
- Cross-language answerable cases: Turkish query → English source, 22; English query → Turkish source, 22.
- All cases use the synthetic Knowledge Base scope `[1]` and fixed `K=3`. The corpus includes similar policy terms, close but different thresholds, API token versus browser-session expiry, record versus backup retention, travel versus procurement limits, and archived/current 2024/2025 travel rules.
- Rebuild with `python -m evaluation.corpora.compact_multilingual_v1.generator`. Determinism, fingerprint, labels, scope, and case counts are tested. The corpus contains no real company, customer, employee, credential, email, or production data.

## Model provenance and execution

| Profile | Exact revision | License | Dimensions / maximum input | Artifact and preprocessing |
| --- | --- | --- | --- | --- |
| Baseline — `sentence-transformers/all-MiniLM-L6-v2` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 | 384 / 256 tokens | Cached pinned `model.safetensors`; original unprefixed query and passage text |
| Candidate — `intfloat/multilingual-e5-small` | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | MIT | 384 / 512 tokens; model card lists 94 languages | Pinned `model.safetensors` (~471 MB; expected SHA-256 `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477`); `query: ` and `passage: ` prefixes |

The [pinned MiniLM snapshot](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41) identifies the cached baseline revision and Apache-2.0 license. The [pinned E5 snapshot](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3) identifies the candidate revision, MIT license, 94-language metadata, and safetensors artifact. Equal dimension does not make these vector spaces compatible.

Hardware: MacBook Pro, Apple M1 Pro, 16 GB unified memory, arm64. Runtime: SentenceTransformers + PyTorch 2.14.1. `torch.backends.mps.is_built()` was true but `is_available()` was false, so the measured baseline ran on CPU. MPS unavailability is not a benchmark failure. The runner dynamically reports the selected device and runs an offline 384-dimensional smoke check before indexing.

Provisioning result: no complete E5 snapshot was present in the Hugging Face cache, SentenceTransformers cache, or project model directories. One bounded official Hugging Face snapshot attempt used the exact revision, `HF_HUB_DISABLE_XET=1`, `HF_HUB_DOWNLOAD_TIMEOUT=120`, and one worker. It was stopped cleanly after approximately 14 minutes with `model.safetensors` still incomplete at 230,686,720 bytes; the partial file was not deleted and was not loaded. No further provisioning retry was made. The local manual-placement target is ignored by Git under `models/compact-multilingual-validation-v2/e5-small-614241f622f53c4eeff9890bdc4f31cfecc418b3/`; its local `README.txt` records the required pinned files and digest. The default Hugging Face cache’s earlier incomplete entry is also preserved. A complete snapshot must be hash-verified and load offline before any E5 benchmark.

## Fixed benchmark conditions

Both profiles use the same versioned corpus, chunking settings, and `K=3`. The experiment changes only the embedding profile and its model-specific input preprocessing. Reranking, adaptive retrieval, BM25/hybrid retrieval, HyDE, query rewriting, and generation are disabled. The runner rejects unpinned snapshot paths, missing/empty safetensors, profile/prefix mismatch, vector-dimension mismatch, and dataset/document corpus-version mismatch. It uses profile-derived vector-space identities and separate temporary local Qdrant collections; it never connects to the production Qdrant URL. The serialized result is aggregate-only and omits questions, document text, and local model paths.

## Results

`—` means not measured because E5 provisioning did not complete; it is not a zero score.

| Metric | MiniLM baseline | E5 candidate |
| --- | ---: | ---: |
| Overall answerable Hit@3 | 0.6136 (81/132) | — |
| Overall MRR | 0.5530 | — |
| Source accuracy | 0.2045 | — |
| Fact coverage | 0.6136 | — |
| Rank 1 / rank 2 / rank 3 | 67 / 8 / 6 | — |
| Misses | 51 | — |
| English Hit@3 / MRR / fact coverage | 0.6667 / 0.6414 / 0.6667 (66 cases) | — |
| Turkish Hit@3 / MRR / fact coverage | 0.5606 / 0.4646 / 0.5606 (66 cases) | — |
| Turkish query → English source Hit@3 / MRR | 0.0000 / 0.0000 (0/22) | — |
| English query → Turkish source Hit@3 / MRR | 0.0000 / 0.0000 (0/22) | — |
| Hard-negative Hit@3 / MRR / fact coverage | 0.9091 / 0.8144 / 0.9091 (44 cases) | — |
| Confusable hard-negative documents in top 3 | 17 | — |
| No-answer cases retrieving a designated confusable document | 17/24; 21 such top-3 results | — |
| English / Turkish no-answer confusable cases | 9/12 / 8/12 | — |

The MiniLM cross-language result is a baseline observation for this small synthetic corpus only. It does not establish that E5 will improve cross-language retrieval.

## CPU performance and resource measurements

| Measurement | MiniLM CPU baseline | E5 |
| --- | ---: | ---: |
| Model load | 4,507.118 ms | — |
| Document embedding | 327.461 ms for 44 chunks (134.367 chunks/s) | — |
| Qdrant upsert / total indexing wall time | 104.672 / 439.476 ms | — |
| Query embedding median / p95 | 9.287 / 13.035 ms | — |
| Qdrant retrieval median / total retrieval median | 0.383 / 9.698 ms | — |
| Vectors / dimensions | 44 / 384 | — |
| Raw float32 vectors / isolated Qdrant directory | 67,584 / 225,802 bytes | — |
| Peak process RSS | 770,129,920 bytes (about 735 MiB) | — |

Peak RSS is a process high-water mark, not model-only memory. Qdrant directory size is a local ephemeral-index measurement, not a production storage estimate. E5 latency, memory, indexing, storage, English regression, and M1 Pro practicality remain unknown because no E5 inference ran.

## Limitations and recommendation

This 44-document synthetic set is intentionally small, with one chunk per document under the current local chunking configuration. Fact coverage uses deterministic normalized substring matching rather than semantic judging. No generation quality, refusal quality, authorization, real-document behavior, or tenant isolation is evaluated here. The 2024/2025 and numeric hard negatives are controlled fictional examples and do not substitute for a larger human-reviewed workload. All retrieval claims are limited to this corpus and this pinned baseline revision.

1. Is the new benchmark reproducible? **Yes.** The generator, checked-in JSON, manifest, stable fingerprint, and deterministic tests agree.
2. Did E5 materially improve Turkish? **Unknown; blocked before E5 inference.**
3. Did E5 materially improve cross-language retrieval? **Unknown; blocked before E5 inference.**
4. Did English quality regress? **Unknown; no paired E5 result.**
5. What performance/resource cost did E5 add? **Unknown; no E5 load or inference was measured.** MiniLM’s measured CPU baseline is listed above.
6. Is E5 practical on M1 Pro 16 GB? **Not established.** The 471 MB artifact size alone is not a memory or latency measurement.
7. Should E5 become the validated Compact Multilingual candidate? **No, not yet. Keep the profile experimental.**
8. Should production remain unchanged until controlled reindex/profile activation exists? **Yes.** Keep MiniLM and `RAG_TOP_K=3`; do not reindex or activate profile switching.
9. Next milestone: **manually provision the exact official E5 safetensors and tokenizer/config files into the ignored model target, verify the pinned digest, load fully offline, then rerun this exact paired K=3 benchmark.** Do not reuse or reconstruct the older private 92-case corpus.
