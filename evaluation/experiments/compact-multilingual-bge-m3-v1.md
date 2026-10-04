# BGE-M3 dense-only multilingual embedding benchmark v1

## Decision

**Classification B — retrieval quality is strong, but the resource profile is too costly to call “Compact”; consider a Balanced Multilingual profile.** On the fictional canonical corpus, BGE-M3 reaches 130/132 answerable Hit@3 (0.9848) and improves over fresh E5-base by 20/132 cases (+0.1515). It substantially closes the canonical Turkish-query → English-source gap (21/22 at K=3, versus 7/22 for E5-base) while preserving/improving EN→TR (22/22 versus 15/22). The matched mirror has a zero K=3 directional recall gap (20/20 in both directions), compared with E5-base’s 7-point gap (18/20 versus 20/20; 0.35 versus 0.90).

The cost is material: a 2.271 GB safetensors artifact, 1024-dimensional vectors, 1.078 GiB process peak RSS, 28.709 ms median query-embedding-plus-retrieval (2.41× E5-base and 4.85× MiniLM in this run), and 24% more measured local Qdrant directory storage than E5-base. Hard-negative expected-source recovery is 44/44, but confusable-source hits rise to 26 (versus 23 for E5-base). No-answer confusable *cases* improve slightly against E5-base (19/24 vs. 20/24), while confusable source results rise (30 vs. 25); this is mixed, not an abstention result. The next single research milestone is a **controlled Balanced Multilingual profile migration/index-activation design review**. This is a design recommendation only, not an activation or migration.

BGE-M3 remains evaluation-only and inactive. Production remains `sentence-transformers/all-MiniLM-L6-v2` with `RAG_TOP_K=3`. No production index, document, profile, retrieval architecture, or user data was changed; no live reindex occurred.

## Model and reproducibility

| Field | Verified value |
| --- | --- |
| Model | `BAAI/bge-m3` |
| Immutable revision | `31e47391fcbda65be526abe98e646b3c6cd845a8` |
| License | MIT |
| Use in this experiment | Single dense vector + normalized embeddings + isolated Qdrant cosine search only |
| Dense dimension / max input | 1024 / 8192 tokens |
| Query / passage preprocessing | No prefix for either; no E5-style instruction |
| Safe artifact | `model.safetensors` |
| Artifact size | 2,271,064,456 bytes |
| Artifact SHA-256 | `993b2248881724788dcab8c644a91dfd63584b6e5604ff2037cb5541e1e38e7e` |
| Inference backend / common device | SentenceTransformers / PyTorch, `mps:0` |
| Loading contract | Offline, local files only, `trust_remote_code=False`, safetensors required |

The immutable [upstream revision tree](https://huggingface.co/BAAI/bge-m3/tree/31e47391fcbda65be526abe98e646b3c6cd845a8), [model card](https://huggingface.co/BAAI/bge-m3), and [pinned `model.safetensors` metadata](https://huggingface.co/BAAI/bge-m3/blob/31e47391fcbda65be526abe98e646b3c6cd845a8/model.safetensors) were checked before running. Only the required config/tokenizer files and the safetensors weights were provisioned into the ignored project `models/` directory; no pickle weights were used. All four models passed a fresh MPS load/encode preflight in this environment with finite, normalized vectors and their expected dimensions and maximum lengths. The benchmark itself ran as four separate fresh processes, all on MPS; no historical CPU timings were used.

The unchanged canonical corpus fingerprint was recomputed as `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b` (44 documents; 156 cases: 132 answerable and 24 no-answer). The unchanged matched mirror fingerprint was recomputed as `95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833955e188c` (40 documents; 40 cases; 20 per direction). Each model used its own temporary Qdrant index. Retrieval remained dense-only cosine at fixed K=3: no sparse vectors, BM25, hybrid, ColBERT, reranker, query rewriting, HyDE, generation, adaptive retrieval, threshold, or abstention logic.

The committed report contains aggregate metrics only. Raw benchmark JSON, temporary Qdrant stores, model paths, weights, and private content were not committed.

## Fresh canonical fixed-K comparison

All answerable metrics use 132 cases except the per-language and cross-language rows noted in labels. Fact coverage is the existing retrieved-text fact check; this corpus has one expected fact per answerable case, so it equals Hit@3 here. Source accuracy is relevant returned sources / returned sources.

| Model | Overall Hit@3 / MRR | Source accuracy | Fact coverage | EN Hit@3 / MRR (66) | TR Hit@3 / MRR (66) | TR→EN Hit@3 / MRR (22) | EN→TR Hit@3 / MRR (22) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiniLM | 0.6136 / 0.5530 | 0.2045 | 0.6136 | 0.6667 / 0.6414 | 0.5606 / 0.4646 | 0/22, 0.0000 / 0.0000 | 0/22, 0.0000 / 0.0000 |
| E5-small | 0.7348 / 0.6970 | 0.2449 | 0.7348 | 0.8030 / 0.7348 | 0.6667 / 0.6591 | 0/22, 0.0000 / 0.0000 | 9/22, 0.4091 / 0.2879 |
| E5-base | 0.8333 / 0.7538 | 0.2778 | 0.8333 | 0.8939 / 0.8005 | 0.7727 / 0.7071 | 7/22, 0.3182 / 0.1818 | 15/22, 0.6818 / 0.4470 |
| **BGE-M3 dense** | **0.9848 / 0.9533** | **0.3283** | **0.9848** | **0.9848 / 0.9571** | **0.9848 / 0.9495** | **21/22, 0.9545 / 0.8485** | **22/22, 1.0000 / 0.9470** |

## Deep-rank cross-language coverage

Recall counts are over 22 canonical cases in each direction. MRR columns are truncated at the indicated rank. The rank-bucket vector order is `rank 1 / rank 2 / rank 3 / rank 4–5 / rank 6–10 / rank 11–20 / beyond 20 or miss`.

| Model / direction | Recall@3 / @5 / @10 / @20 | MRR@3 / @5 / @10 | Rank buckets |
| --- | ---: | ---: | --- |
| MiniLM TR→EN | 0 / 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 / 0 / 0 / 0 / 22 |
| E5-small TR→EN | 0 / 5 / 7 / 11 | 0 / 0.0523 / 0.0633 | 0 / 0 / 0 / 5 / 2 / 4 / 11 |
| E5-base TR→EN | 7 / 10 / 13 / 21 | 0.1818 / 0.2136 / 0.2304 | 2 / 2 / 3 / 3 / 3 / 8 / 1 |
| **BGE-M3 TR→EN** | **21 / 22 / 22 / 22** | **0.8485 / 0.8576 / 0.8576** | **17 / 2 / 2 / 1 / 0 / 0 / 0** |
| MiniLM EN→TR | 0 / 1 / 3 / 7 | 0 / 0.0114 / 0.0235 | 0 / 0 / 0 / 1 / 2 / 4 / 15 |
| E5-small EN→TR | 9 / 12 / 17 / 21 | 0.2879 / 0.3174 / 0.3462 | 5 / 0 / 4 / 3 / 5 / 4 / 1 |
| E5-base EN→TR | 15 / 19 / 21 / 22 | 0.4470 / 0.4902 / 0.5023 | 6 / 5 / 4 / 4 / 2 / 1 / 0 |
| **BGE-M3 EN→TR** | **22 / 22 / 22 / 22** | **0.9470 / 0.9470 / 0.9470** | **20 / 1 / 1 / 0 / 0 / 0 / 0** |

For BGE-M3 TR→EN, the exact expected-source counts are **21/22 in top 3, 22/22 in top 5, 22/22 in top 10, and 22/22 in top 20**. EN→TR is **22/22 at each cutoff**. BGE-M3 expected-source cosine (median / p95) is 0.5860 / 0.6631 for TR→EN and 0.6329 / 0.6953 for EN→TR. Top-1 minus expected-source margin (median / p95) is approximately 0 / 0.0346 for TR→EN and approximately 0 / 0.0007 for EN→TR.

## Matched mirror corpus

Each direction has 20 cases. Values are recall counts at each cutoff; the last column is the absolute K=3 direction gap.

| Model | TR→EN R@3 / @5 / @10 / @20 | EN→TR R@3 / @5 / @10 / @20 | K=3 gap |
| --- | ---: | ---: | ---: |
| MiniLM | 0 / 0 / 0 / 0 | 0 / 1 / 2 / 6 | 0.00 |
| E5-small | 6 / 7 / 9 / 19 | 10 / 16 / 18 / 20 | 0.20 |
| E5-base | 11 / 14 / 18 / 20 | 18 / 20 / 20 / 20 | 0.35 |
| **BGE-M3 dense** | **20 / 20 / 20 / 20** | **20 / 20 / 20 / 20** | **0.00** |

BGE-M3’s expected mirror source ranked second in every case in both directions (MRR@3 0.5000 for each direction). Thus recall is symmetric at the fixed K while rank-1 precision is not perfect. The measured mirror gap is lower than E5-base’s 0.35; this remains synthetic-corpus evidence, not a general language-pair guarantee.

## Hard negatives and no-answer diagnostics

| Model | Hard-negative expected source in top 3 (44) | Confusable source results in top 3 | No-answer cases with a confusable source (24) | Confusable source results |
| --- | ---: | ---: | ---: | ---: |
| MiniLM | 40/44 | 17 | 17/24 | 21 |
| E5-small | 44/44 | 21 | 18/24 | 25 |
| E5-base | 44/44 | 23 | 20/24 | 25 |
| **BGE-M3 dense** | **44/44** | **26** | **19/24** | **30** |

BGE-M3 preserves full expected-source recovery for the 44 hard-negative cases, but increases confusable co-retrieval versus every comparator; in one case a confusable source ranks above the expected source. No-answer confusable-case count is one lower than E5-base but one higher than E5-small and two higher than MiniLM. Confusable source instances are highest for BGE-M3. Similarity scores are reported only as diagnostics and were not turned into an answerability threshold.

## Tokenization and truncation

Canonical BGE-M3 token counts (median / p95 / maximum; truncated count):

| Input | English | Turkish |
| --- | ---: | ---: |
| Queries (78 each) | 18 / 23 / 23; 0 | 20 / 24 / 26; 0 |
| Documents (22 each) | 33 / 42 / 44; 0 | 36 / 45 / 51; 0 |

Mirror BGE-M3 token counts:

| Input | English | Turkish |
| --- | ---: | ---: |
| Queries (20 each) | 14 / 18 / 18; 0 | 15.5 / 19 / 20; 0 |
| Documents (20 each) | 24 / 27 / 27; 0 | 25.5 / 31 / 31; 0 |

No corpus input was truncated for BGE-M3 or the other models. The corpora contain short texts; the 8192-token limit does not establish better long-document product retrieval.

## Resource cost (fresh process per model)

Times are milliseconds on the same Apple MPS host; retrieval median is Qdrant-only and total retrieval is query embedding plus retrieval. Peak RSS is process high-water mark, not model-only memory and may not include all unified-memory allocations.

| Model | Load | Query embed median / p95 | Qdrant median | Total retrieval median | Doc embed (44) | chunks/s | Upsert | Index wall | Peak RSS MiB | Safetensors bytes | Raw vector bytes | Qdrant dir bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiniLM | 4459.573 | 5.600 / 6.442 | 0.315 | 5.923 | 134.378 | 327.435 | 37.910 | 176.522 | 705.7 | 90,868,376 | 67,584 | 225,815 |
| E5-small | 4353.721 | 9.427 / 10.628 | 0.339 | 9.754 | 140.629 | 312.880 | 29.164 | 172.565 | 1128.9 | 470,641,600 | 67,584 | 225,815 |
| E5-base | 4826.821 | 11.533 / 12.869 | 0.377 | 11.888 | 362.986 | 121.217 | 32.805 | 398.904 | 1059.1 | 1,112,201,288 | 135,168 | 373,271 |
| **BGE-M3 dense** | **6129.638** | **28.264 / 37.348** | **0.414** | **28.709** | **628.097** | **70.053** | **39.464** | **672.423** | **1077.9** | **2,271,064,456** | **180,224** | **463,384** |

There are 44 document vectors in this isolated index: the BGE-M3 raw float32 payload is 180,224 bytes (4× MiniLM/E5-small; 1.33× E5-base). The measured Qdrant directory is 2.05× MiniLM/E5-small and 1.24× E5-base. BGE-M3’s safetensors file is 25.0× MiniLM, 4.82× E5-small and 2.04× E5-base. Peak RSS is 1.53× MiniLM, 0.96× E5-small and 1.02× E5-base. Median total query retrieval is 4.85× MiniLM, 2.94× E5-small and 2.41× E5-base in this run. These small one-off timings and directory sizes are directional measurements, not deployment capacity guarantees.

## Limitations and product gate

- Fictional, short-text corpora do not establish customer workload performance or long-document behavior.
- No generated answer quality, citation correctness, production concurrency, multi-tenant deployment sizing, cold-start reliability, or LLM latency was measured.
- No-answer confusability is retrieval overlap only; no abstention behavior or threshold was evaluated.
- Dense-only results say nothing about BGE-M3 sparse, ColBERT/multi-vector, hybrid, or reranker quality; those paths were excluded.
- The large safetensors and slower embedding/indexing path rule out describing this candidate as compact on this evidence. Resource feasibility must be reviewed for a future Balanced Multilingual option.

**Product gate: B.** BGE-M3 dense retrieval is substantially stronger on these fixed corpora, including the difficult TR→EN direction and mirror symmetry, but its model size, 1024-dimensional index, query latency and indexing throughput are not a compact resource profile. A bounded reranker is not justified by this run: expected-source coverage is 22/22 by rank 5 and 22/22 by rank 20 for canonical TR→EN. A dense+sparse experiment is also not justified yet by these dense-only measurements. Keep production unchanged and review a controlled Balanced Multilingual migration/index-activation design as the single next research milestone; do not implement it here.
