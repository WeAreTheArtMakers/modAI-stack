# Compact Multilingual: pinned E5-base offline evaluation

## Decision

**E5-base is not yet a validated Compact Multilingual profile.** It materially improves the unresolved Turkish-query → English-source direction on the canonical corpus (Hit/Recall@3: 0/22 → 7/22; Recall@10: 7/22 with E5-small → 13/22), but the directional deficit remains substantial: EN→TR is 15/22 at K=3, and the matched mirror is 11/20 TR→EN versus 18/20 EN→TR. The mirror K=3 asymmetry is 35 percentage points (20 points for E5-small), so this candidate does **not** reduce the matched-set directional asymmetry. Nine of 22 canonical TR→EN expected sources still lie beyond K=10. This is case B of the product gate; evaluate a pinned `BAAI/bge-m3` candidate next, without changing production. A bounded reranker is not the next milestone because candidate coverage at K=10 remains incomplete.

E5-base remains experimental, inactive, non-selectable. No production model, vector index, Knowledge Base, profile switch, reranker, adaptive retrieval, hybrid retrieval, threshold, or abstention behavior was changed. Production stays on `sentence-transformers/all-MiniLM-L6-v2` with `RAG_TOP_K=3`.

## Reproducibility and safety

- Run: one fresh three-way lifecycle on the same host and **MPS (`mps:0`) for every model**; no historical CPU latency is compared. Host: Apple M1 Pro, arm64, 16 GiB unified memory (`hw.memsize=17179869184`); PyTorch 2.14.1, MPS built and available outside the restricted sandbox. All three pinned models passed offline MPS load/encode preflight. The sandbox itself reported MPS unavailable and was not used for measurements.
- Canonical `compact-multilingual-v1`: fingerprint `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b`, 44 fictional documents, 156 cases (132 answerable, 24 no-answer).
- Matched mirror `cross-language-mirror-v1`: fingerprint `95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833595e188c`, 40 documents and 40 directional cases (20 per direction). Both fingerprints were recomputed from the local corpus files and matched their manifests.
- Offline controls: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`, local-only SentenceTransformers loading, safetensors, no remote model ID. The E5-base snapshot contained all nine required non-empty files. `model.safetensors` size was **1,112,201,288 bytes** and SHA-256 was **`a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7`**. The offline smoke test covered Turkish and English queries/passages in all four language pairings; finite, normalized 768-dimensional embeddings, tokenizer, and 512-token maximum were verified.
- Same documents, cases, production chunk settings, local Qdrant cosine configuration, user/KB filter semantics, and fixed K=3. Generation, reranking, adaptive retrieval, BM25, hybrid search, HyDE, rewriting, and abstention were disabled. Each model had a separate ephemeral Qdrant directory and a collection identity binding model, revision, dimensions, preprocessing, and corpus fingerprint. Neither model weights nor raw result files are committed.

| Model | Revision | License | Vector | Preprocessing | Safetensors SHA-256 |
| --- | --- | --- | ---: | --- | --- |
| `sentence-transformers/all-MiniLM-L6-v2` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 | 384 | No prefix | `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` |
| `intfloat/multilingual-e5-small` | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | MIT | 384 | `query: ` / `passage: ` | `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477` |
| `intfloat/multilingual-e5-base` | `d128750597153bb5987e10b1c3493a34e5a4502a` | MIT | 768 | `query: ` / `passage: ` | `a18a44fad1d0b46ded15928144138cff1135d5cc8233bdd90be5f18822de09a7` |

MiniLM came from the pinned local Hugging Face snapshot; both E5 models came from the ignored, manually provisioned project model directories. Inference backend was SentenceTransformers / PyTorch for all three. E5-base inputs were prefixed exactly once. All corpus inputs fit model limits; no truncation was observed in the canonical diagnostics.

## Fixed K=3 quality (fresh common-device runs)

All rates are fractions. `source accuracy` is relevant returned sources / returned sources; `fact coverage` is expected factual strings found in retrieved chunks, **not generated-answer quality**. In this single-fact corpus, fact coverage happens to equal Hit@3.

| Metric | MiniLM | E5-small | E5-base |
| --- | ---: | ---: | ---: |
| Overall Hit@3 / fact coverage (132) | 0.6136 | 0.7348 | **0.8333** |
| Overall MRR | 0.5530 | 0.6970 | **0.7538** |
| Overall source accuracy | 0.2045 | 0.2449 | **0.2778** |
| Overall rank 1 / 2 / 3 / miss | 67 / 8 / 6 / 51 | 89 / 2 / 6 / 35 | **92 / 9 / 9 / 22** |
| English Hit@3 / fact coverage (66) | 0.6667 | 0.8030 | **0.8939** |
| English MRR | 0.6414 | 0.7348 | **0.8005** |
| Turkish Hit@3 / fact coverage (66) | 0.5606 | 0.6667 | **0.7727** |
| Turkish MRR | 0.4646 | 0.6591 | **0.7071** |
| Hard-negative Hit@3 / fact coverage (44) | 0.9091 | 1.0000 | **1.0000** |
| Hard-negative MRR | 0.8144 | **0.9886** | 0.9735 |
| Hard-negative confusable source results in top 3 | 17 | 21 | **23** (worse) |
| No-answer cases with confusable source in top 3 (24) | 17 | 18 | **20** (worse) |
| No-answer confusable source results in top 3 | 21 | 25 | 25 |

E5-base versus MiniLM: overall Hit@3 +0.2197, Turkish +0.2121, English +0.2272, overall MRR +0.2008. Versus E5-small: overall Hit@3 +0.0985, Turkish +0.1060, English +0.0909, overall MRR +0.0568. Hard-negative expected sources remain 44/44 at K=3, but confusable co-retrieval increases by 2 versus E5-small and 6 versus MiniLM; one E5-base hard-negative case ranks a confusable source above the expected source. No-answer confusability rises by 2 cases versus E5-small and 3 versus MiniLM. These are retrieval observations only; no abstention threshold was fitted.

## Cross-language rank and recall

Each canonical direction has 22 answerable cases. At K=3, Hit@3 equals Recall@3 because each case has one expected source. MRR below is truncated to K=3. Rank buckets are based on a separate deep-rank run over the same pinned models/corpus; `>10` includes ranks 11–20 and beyond-window misses.

| Canonical direction / model | Hit@3 | MRR@3 | R@1 | R@3 | R@5 | R@10 | Rank 1 / 2–3 / 4–5 / 6–10 / >10 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| TR→EN MiniLM | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0 / 0 / 0 / 0 / 22 |
| TR→EN E5-small | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.2273 | 0.3182 | 0 / 0 / 5 / 2 / 15 |
| TR→EN E5-base | **0.3182** | **0.1818** | 0.0909 | 0.3182 | 0.4545 | 0.5909 | **2 / 5 / 3 / 3 / 9** |
| EN→TR MiniLM | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0455 | 0.1364 | 0 / 0 / 1 / 2 / 19 |
| EN→TR E5-small | 0.4091 | 0.2879 | 0.2273 | 0.4091 | 0.5455 | 0.7727 | 5 / 4 / 3 / 5 / 5 |
| EN→TR E5-base | **0.6818** | **0.4470** | 0.2727 | 0.6818 | 0.8636 | 0.9545 | **6 / 9 / 4 / 2 / 1** |

On the 20-fact matched mirror, each direction has 20 cases:

| Model | TR→EN R@1 / R@3 / R@5 / R@10 | EN→TR R@1 / R@3 / R@5 / R@10 | K=3 direction gap |
| --- | --- | --- | ---: |
| MiniLM | 0 / 0 / 0 / 0 | 0 / 0 / 0.05 / 0.10 | 0 points |
| E5-small | 0 / 0.30 / 0.35 / 0.45 | 0 / 0.50 / 0.80 / 0.90 | 20 points |
| E5-base | 0 / **0.55 / 0.70 / 0.90** | 0 / **0.90 / 1.00 / 1.00** | **35 points** |

E5-base improves canonical TR→EN R@3 by +0.3182 versus both MiniLM and E5-small; R@10 is +0.5909 versus MiniLM and +0.2727 versus E5-small. It also improves EN→TR R@3 by +0.6818 versus MiniLM and +0.2727 versus E5-small. Canonical absolute K=3 gap narrows slightly (40.91 → 36.36 points versus E5-small), but the matched mirror gap *widens* (20 → 35 points). Therefore the stronger embedding improves both directions but does not establish symmetric cross-language retrieval.

## Performance and footprint

Times are milliseconds unless specified. Cold load is separate from warm queries. Each model ran in a separate process, sequentially on the same MPS device; caches, filesystem state, and process RSS can influence one-off measurements. Query retrieval is embedding + local Qdrant search, not LLM answer latency.

| Metric | MiniLM | E5-small | E5-base |
| --- | ---: | ---: | ---: |
| Cold model load | 4,737.686 | 5,263.171 | 5,596.462 |
| Document embedding, 44 chunks | 189.407 | 159.894 | 402.110 |
| Document throughput, chunks/s | 232.304 | 275.182 | 109.423 |
| Qdrant upsert | 18.597 | 22.283 | 23.564 |
| Total indexing wall | 211.282 | 186.132 | 431.102 |
| Warm query embedding median / p95 | 6.205 / 8.112 | 10.666 / 12.136 | **12.540 / 19.552** |
| Qdrant search median | 0.389 | 0.442 | 0.483 |
| Total retrieval median | 6.632 | 11.109 | **13.016** |
| Peak process RSS, MiB | 699.1 | 1068.7 | 1070.4 |
| Isolated Qdrant directory, bytes | 225,815 | 225,815 | **373,271** |
| Raw float32 payload, bytes (44 vectors) | 67,584 | 67,584 | **135,168** |

E5-base adds 1.907 ms warm median retrieval over E5-small and 6.384 ms over MiniLM in this run; document embedding is 2.52× E5-small time. The 768-dimensional raw float32 payload is exactly twice 384-dimensional payload (3,072 versus 1,536 bytes/vector); measured isolated Qdrant storage is about 1.65× here, not assumed to double. E5-base peak process RSS is about 1.12 GB, only ~1.8 MB above the separate E5-small process in this measurement. This is a process high-water mark and does **not** isolate model memory or fully account for unified-memory GPU allocations. The measured single-model workload ran on M1 Pro/16 GiB without instability, so it appears locally practical, but concurrency and production-size corpus capacity are unproven.

## Interpretation and limits

The answer to the product questions is: E5-base **partly** fixes TR→EN; it does **not** remove the matched-direction asymmetry; Turkish improves; English does not regress; hard-negative expected-source coverage holds but confusable competition increases; no-answer confusability worsens; warm median retrieval rises to 13.016 ms; vectors double and local index grows to 373,271 bytes; the small isolated workload is practical on this M1 Pro but not a production capacity test. Therefore E5-base is **not validated** for Compact Multilingual. The single next milestone is a pinned, offline `BAAI/bge-m3` retrieval comparison, subject to deliberate provisioning and the same quality/resource gate.

These fictional, short-document corpora are diagnostic, not customer evidence. No LLM responses, citation correctness, answerability calibration, long-document retrieval, concurrency, or end-to-end service latency were measured. The local Qdrant directory is not production storage. MPS availability differs inside versus outside the restricted sandbox; the actual benchmark device was recorded per model as `mps:0`. Do not extrapolate the absolute small-corpus latencies or memory to large deployments.
