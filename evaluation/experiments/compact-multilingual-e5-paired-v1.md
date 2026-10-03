# Compact Multilingual E5-small paired benchmark v1

## Decision

**E5-small is promising but is not a validated Compact Multilingual candidate.** It improved overall, English, and Turkish answerable retrieval, and materially improved English-query → Turkish-source retrieval. However, Turkish-query → English-source retrieval remained 0/22, while no-answer confusability increased from 17/24 to 18/24 cases and from 21 to 25 designated confusable sources in the top three. The language-direction gap and increased confusability fail the current product gate.

Keep Compact Multilingual experimental, inactive, and non-selectable. Production remains on `sentence-transformers/all-MiniLM-L6-v2`, with `RAG_TOP_K=3`; no production model, profile, collection, Knowledge Base, or real document was changed. The next milestone is **Evaluate multilingual-e5-base** using this same paired protocol.

## Corpus and protocol

- Corpus: `compact-multilingual-v1`; fingerprint: `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b`.
- Dataset fingerprint: `12fb1371a48a5b4b019f75e5bb423ebbfe2ac0d257d214c38581e6c8f540ee49`.
- 44 fictional documents, 156 cases (132 answerable, 24 no-answer), 66 English and 66 Turkish answerable queries; 22 cases in each cross-language direction.
- The checked-in generator was rerun immediately before the experiment; its manifest reproduced the expected fingerprint and counts.
- Fixed `K=3`, identical documents and cases, same chunker settings (`chunk_size=700`, `chunk_overlap=100`), same local Qdrant configuration. Each model used its own temporary Qdrant directory and profile-derived collection/vector-space identity.
- 44 chunks / vectors per run. No generation, reranking, adaptive retrieval, BM25, hybrid retrieval, HyDE, or query rewriting.
- The only semantic variable was the model and its required input preprocessing. MiniLM used original text; E5 used its documented query/passage prefixes.
- Aggregate-only result files were held under `/private/tmp` and are not committed. Questions, retrieved passages, local model paths, model weights, and caches are absent from the report.

## Models and offline provenance

| Profile | Exact model / revision | License | Dimension | Preprocessing | Artifact verification |
| --- | --- | --- | ---: | --- | --- |
| Baseline | [`sentence-transformers/all-MiniLM-L6-v2`](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/tree/1110a243fdf4706b3f48f1d95db1a4f5529b4d41) / `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 | 384 | identity; original text | Pinned local Hugging Face cache snapshot; safetensors SHA-256 `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` |
| Candidate | [`intfloat/multilingual-e5-small`](https://huggingface.co/intfloat/multilingual-e5-small/tree/614241f622f53c4eeff9890bdc4f31cfecc418b3) / `614241f622f53c4eeff9890bdc4f31cfecc418b3` | MIT | 384 | `query: <text>` / `passage: <text>` | Manually provisioned ignored local snapshot; all required non-empty files verified; `model.safetensors` SHA-256 matched `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477` |

Both benchmark processes used local model paths with `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1`, `HF_DATASETS_OFFLINE=1`, telemetry disabled, and SentenceTransformers `local_files_only=True`; no download fallback was enabled. E5’s tokenizer and model initialized from the local snapshot. Turkish, English, and both cross-language query/passage encoding combinations produced finite 384-dimensional vectors. The runner also checked the pinned revision, required files, and E5 safetensors digest before loading.

Hardware context: MacBook Pro M1 Pro, 16 GB unified memory, arm64; macOS 26.0.1. PyTorch 2.14.1, SentenceTransformers 5.7.0. `torch.backends.mps.is_built()` was true but `is_available()` was false, so both runs used CPU. Direct CPU/RAM sysctl inspection was denied in this execution context; the model/device facts and host specification are not inferred from benchmark timings.

## Retrieval quality

Metrics are computed over the same 132 answerable cases unless otherwise noted. The `rank 1 / 2 / 3` columns count the first rank of the expected source; misses have no expected source in top three.

| Overall metric | MiniLM | E5-small | E5 − MiniLM |
| --- | ---: | ---: | ---: |
| Hit@3 | 0.6136 (81/132) | 0.7348 (97/132) | +12.12 percentage points |
| MRR | 0.5530 | 0.6970 | +0.1440 |
| Source accuracy | 0.2045 | 0.2449 | +0.0404 |
| Fact coverage | 0.6136 | 0.7348 | +12.12 percentage points |
| Rank 1 / rank 2 / rank 3 | 67 / 8 / 6 | 89 / 2 / 6 | — |
| Misses | 51 | 35 | −16 |

| Query language | MiniLM Hit@3 / MRR / fact coverage | E5-small Hit@3 / MRR / fact coverage | Hit@3 delta |
| --- | ---: | ---: | ---: |
| English (66) | 0.6667 / 0.6414 / 0.6667 | 0.8030 / 0.7348 / 0.8030 | +13.63 pp |
| Turkish (66) | 0.5606 / 0.4646 / 0.5606 | 0.6667 / 0.6591 / 0.6667 | +10.61 pp |

| Cross-language direction (22 each) | MiniLM Hit@3 / MRR | E5-small Hit@3 / MRR | Hit@3 delta |
| --- | ---: | ---: | ---: |
| Turkish query → English source | 0.0000 / 0.0000 (0/22) | 0.0000 / 0.0000 (0/22) | 0 pp |
| English query → Turkish source | 0.0000 / 0.0000 (0/22) | 0.4091 / 0.2879 (9/22) | +40.91 pp |

| Hard-negative metric (44 cases) | MiniLM | E5-small |
| --- | ---: | ---: |
| Hit@3 / MRR / fact coverage | 0.9091 / 0.8144 / 0.9091 | 1.0000 / 0.9886 / 1.0000 |
| Designated confusable document hits in top three | 17 | 21 |

| No-answer confusability (24 cases) | MiniLM | E5-small |
| --- | ---: | ---: |
| Cases with ≥1 designated confusable source in top three | 17/24 | 18/24 |
| Designated confusable source results in top three | 21 | 25 |
| English cases | 9/12 cases; 10 sources | 8/12 cases; 12 sources |
| Turkish cases | 8/12 cases; 11 sources | 10/12 cases; 13 sources |

Thus E5 improved answerable retrieval quality and both per-language aggregate scores, but cross-language gains were one-way only. The hard-negative expected-source metrics improved while confusable-source frequency also rose; no-answer confusability worsened. Similarity remains retrieval evidence, not an answerability or abstention signal.

## Performance and resource measurements

| Measurement | MiniLM CPU | E5-small CPU | E5 change |
| --- | ---: | ---: | ---: |
| Process-cold model initialization | 4,484.143 ms | 5,244.042 ms | +759.899 ms (+16.9%) |
| Document embedding, 44 chunks | 179.288 ms | 195.745 ms | +16.457 ms (+9.2%) |
| Document embedding throughput | 245.415 chunks/s | 224.782 chunks/s | −8.4% |
| Qdrant upsert | 28.447 ms | 30.647 ms | +2.200 ms |
| Total indexing wall time | 212.432 ms | 231.816 ms | +19.384 ms (+9.1%) |
| Warm query embedding median / p95 | 11.140 / 12.831 ms | 21.730 / 25.036 ms | median +10.590 ms (+95.1%); p95 +12.205 ms |
| Qdrant retrieval median | 0.403 ms | 0.415 ms | +0.012 ms |
| Warm total retrieval median | 11.570 ms | 22.249 ms | +10.679 ms (+92.3%) |
| Vectors / dimension | 44 / 384 | 44 / 384 | same |
| Raw float32 vectors | 67,584 bytes | 67,584 bytes | same |
| Temporary Qdrant directory | 225,802 bytes | 225,802 bytes | same |
| Process peak RSS high-water mark | 789,790,720 bytes (753.5 MiB) | 1,135,886,336 bytes (1,083.2 MiB) | +346,095,616 bytes (+330.1 MiB; +43.8%) |

“Process-cold” means a new benchmark process initialized the model; the OS file cache was not forcibly cleared. Warm query latency is reported separately from initialization. RSS is whole-process peak, not model-only memory. These CPU measurements are for one synthetic 44-chunk local index; they do not include the full application stack, concurrent users, real document distributions, or production storage overhead.

## Product-gate answers and limitations

1. **Did E5 materially improve Turkish?** Yes on this corpus: Hit@3 +10.61 pp and MRR +0.1945.
2. **Did it materially improve Turkish-query → English-source?** No: still 0/22.
3. **Did it materially improve English-query → Turkish-source?** Yes: 0/22 to 9/22; MRR 0.2879.
4. **Did English regress?** No; English Hit@3 increased by 13.63 pp and MRR by 0.0934.
5. **Did hard-negative quality regress?** Expected-source Hit@3/MRR improved, but designated confusable-source hits rose from 17 to 21, so the distractor trade-off needs follow-up.
6. **Did no-answer confusability improve?** No; it worsened from 17 to 18 cases and 21 to 25 confusable sources in top three.
7. **Warm-query latency cost?** Median embedding +10.590 ms; p95 +12.205 ms; total retrieval median +10.679 ms.
8. **Memory/indexing cost?** Process peak RSS +330.1 MiB; indexing wall time +19.384 ms. The tiny isolated vector-store directory size was unchanged.
9. **Practical on M1 Pro / 16 GB?** The measured CPU process footprint (~1.06 GiB) and ~22.25 ms warm retrieval median appear practical for this small workload. Full product/app memory and real-scale indexing remain unmeasured, so this is not a deployment guarantee.
10. **Validated Compact Multilingual candidate?** No. The unresolved TR→EN result and worse no-answer confusability prevent a clear pass despite promising aggregate gains.
11. **Should production remain unchanged?** Yes. Keep MiniLM, `RAG_TOP_K=3`, current indexes, profile switching disabled, and Compact Multilingual inactive/non-selectable.
12. **Single next milestone:** evaluate pinned `intfloat/multilingual-e5-base` with the same offline paired corpus and quality/resource gates.

Limitations: this is a small, fully synthetic corpus with one chunk per document at current chunk settings. Fact coverage is deterministic normalized substring matching, not semantic human review. No generation quality, abstention behavior, authorization, real-document performance, or multi-user load was evaluated. Results should not be generalized beyond this test corpus and hardware/runtime setup.
