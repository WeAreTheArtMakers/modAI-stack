# Cross-language retrieval diagnostics v1

## Decision

**Classification B — E5-small has a material Turkish-query → English-source weakness on this workload.** On the unchanged canonical corpus, none of the 22 expected sources ranks in the top three; only 7/22 are in the top ten, and 15/22 are below the returned top-20 window. The exact paired fixed-K benchmark was rerun for both pinned models and reproduced the earlier overall results. A separate 20-fact mirrored diagnostic also retained a directional gap, so canonical construction contributes uncertainty but does not explain the whole effect.

Keep E5-small experimental, inactive, and non-selectable. **The next embedding candidate should be the pinned multilingual-e5-base evaluation** because most canonical Turkish→English expected sources are not in a small candidate pool; a reranker cannot rescue sources it never receives. Do not download/provision E5-base as part of this milestone. A top-20 candidate-pool/reranker study remains useful as a later, bounded follow-up, but is not the primary next step indicated by these ranks.

Production is unchanged: `sentence-transformers/all-MiniLM-L6-v2`, `RAG_TOP_K=3`, current production Qdrant and Knowledge Bases. Adaptive retrieval, reranking, profile switching, and abstention/refusal thresholds remain disabled.

## Corpus and protocol

| Set | Version | Fingerprint | Documents | Cases |
| --- | --- | --- | ---: | ---: |
| Canonical, unchanged | `compact-multilingual-v1` | `81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b` | 44 | 156 |
| Supplemental matched diagnostic | `cross-language-mirror-v1` | `95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833595e188c` | 40 | 40 |

The canonical corpus was fingerprint-checked before the run and was not edited. The supplemental set is deterministic and fictional: 20 shared fact structures, each with an English and Turkish source plus a cross-language query in each direction (20 cases per direction). Its opposite-language same-fact document is an explicit confusable. It is diagnostic evidence, not a replacement corpus.

For both models, the canonical full paired protocol used the same chunker (`chunk_size=700`, overlap 100), normalized embeddings, separate temporary local Qdrant collections, cosine distance, and fixed K=3. The cross-language diagnostic then fetched up to 20 hits and reported expected-document ranks after document-level deduplication; the corpora yielded one chunk per document. Non-cross-language cases remained at top 3. No raw questions, passage text, case IDs, local model paths, cache files, or model weights are stored in the aggregate results or this report.

Both model snapshots were already local and ran fully offline on CPU with SentenceTransformers/PyTorch. No model was downloaded during this work.

| Model | Pinned revision | License | Dimensions | Input contract | Safetensors SHA-256 |
| --- | --- | --- | ---: | --- | --- |
| `sentence-transformers/all-MiniLM-L6-v2` | `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` | Apache-2.0 | 384 | Original query and passage text | `53aa51172d142c89d9012cce15ae4d6cc0ca6895895114379cacb4fab128d9db` |
| `intfloat/multilingual-e5-small` | `614241f622f53c4eeff9890bdc4f31cfecc418b3` | MIT | 384 | `query: <text>` / `passage: <text>` | `1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477` |

The benchmark used 384-dimensional finite vectors, `normalize_embeddings=True`, and Qdrant `COSINE`. Qdrant’s expected-source scores agreed with direct dot products over normalized vectors within the runner’s tolerance. Each model/revision/prefix/corpus combination had a distinct vector-space/index identity; vectors were never mixed. E5 prefixes were applied exactly once, MiniLM remained unprefixed, and Turkish characters (`ı İ ğ ş ç ö ü`) were preserved. No preprocessing, tokenization, normalization, or indexing implementation bug was found.

## Canonical deep-rank results

Rank buckets count expected-source document rank. `>20/miss` means the source was not present in the returned top 20; rank 21+ cannot be distinguished from a top-20 miss. Recall and MRR denominators are all 22 cases in that direction.

| Model | Direction | 1 | 2 | 3 | 4–5 | 6–10 | 11–20 | >20 / miss | Finite-rank median |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiniLM | TR query → EN source | 0 | 0 | 0 | 0 | 0 | 0 | 22 | — |
| MiniLM | EN query → TR source | 0 | 0 | 0 | 1 | 2 | 4 | 15 | 12 |
| E5-small | TR query → EN source | 0 | 0 | 0 | 5 | 2 | 4 | 11 | 7 |
| E5-small | EN query → TR source | 5 | 0 | 4 | 3 | 5 | 4 | 1 | 5 |

| Model | Direction | Recall@1 | Recall@3 | Recall@5 | Recall@10 | MRR@3 | MRR@5 | MRR@10 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| MiniLM | TR query → EN source | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| MiniLM | EN query → TR source | 0.0000 | 0.0000 | 0.0455 | 0.1364 | 0.0000 | 0.0114 | 0.0235 |
| E5-small | TR query → EN source | 0.0000 | 0.0000 | 0.2273 | 0.3182 | 0.0000 | 0.0523 | 0.0633 |
| E5-small | EN query → TR source | 0.2273 | 0.4091 | 0.5455 | 0.7727 | 0.2879 | 0.3174 | 0.3462 |

The 6–10 bucket contains only 2/22 TR→EN cases for E5-small; another 4 are in 11–20. Thus raising K or reranking the top ten cannot address most of the direction’s misses. Expected-source similarity itself is not uniformly low: E5’s TR→EN median is 0.7797, but top-1 median is 0.8302 and the median top1-minus-expected margin is 0.0489. This is primarily a ranking/separation problem for sources that are retrieved, alongside a substantial tail outside rank 20.

### Aggregate cosine and rank-margin diagnostics

Expected-source cosine is the best matching chunk of an expected document. Margin is `top1 cosine − expected-source cosine`; a positive value means the best returned chunk scored above the expected source.

| Model | Direction | Score | Min | Median | p95 | Max |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| MiniLM | TR → EN | Expected source | −0.0798 | 0.0277 | 0.1676 | 0.2758 |
| MiniLM | TR → EN | Top 1 | 0.6427 | 0.6912 | 0.7608 | 0.8153 |
| MiniLM | TR → EN | Top1 − expected | 0.4664 | 0.6758 | 0.7300 | 0.8142 |
| MiniLM | EN → TR | Expected source | −0.0706 | 0.0389 | 0.2396 | 0.2730 |
| MiniLM | EN → TR | Top 1 | 0.2290 | 0.4393 | 0.6313 | 0.8033 |
| MiniLM | EN → TR | Top1 − expected | 0.0839 | 0.3869 | 0.5304 | 0.7694 |
| E5-small | TR → EN | Expected source | 0.7461 | 0.7797 | 0.8377 | 0.8511 |
| E5-small | TR → EN | Top 1 | 0.8098 | 0.8302 | 0.8696 | 0.8731 |
| E5-small | TR → EN | Top1 − expected | 0.0023 | 0.0489 | 0.0794 | 0.0855 |
| E5-small | EN → TR | Expected source | 0.7398 | 0.7861 | 0.8391 | 0.8429 |
| E5-small | EN → TR | Top 1 | 0.7983 | 0.8224 | 0.8517 | 0.8916 |
| E5-small | EN → TR | Top1 − expected | 0.0000 | 0.0302 | 0.0695 | 0.0721 |

For E5-small, expected-source cosine ranges overlap closely by direction (p95 0.8377 TR→EN; 0.8391 EN→TR); the gap is more visible in rank outcomes and top-1 margin than in expected-source similarity. For MiniLM, cross-language expected-source scores are near zero and well below the retrieved top-1 scores.

## Full fixed-K paired benchmark rerun

Both profiles were rerun offline against the unchanged canonical corpus with the existing full fixed-K=3 benchmark runner. Quality results reproduce the prior paired report:

| Metric | MiniLM | E5-small |
| --- | ---: | ---: |
| Overall answerable Hit@3 (132 cases) | 0.6136 (81/132) | 0.7348 (97/132) |
| Overall MRR | 0.5530 | 0.6970 |
| English Hit@3 | 0.6667 | 0.8030 |
| Turkish Hit@3 | 0.5606 | 0.6667 |
| TR query → EN source Hit@3 | 0.0000 (0/22) | 0.0000 (0/22) |
| EN query → TR source Hit@3 | 0.0000 (0/22) | 0.4091 (9/22) |

Performance and resource figures are reused from [`compact-multilingual-e5-paired-v1.md`](compact-multilingual-e5-paired-v1.md), not replaced by timing samples from this diagnostic rerun. That prior run recorded warm total retrieval medians of 11.570 ms (MiniLM) and 22.249 ms (E5-small), and peak process RSS of about 753.5 MiB and 1,083.2 MiB respectively.

## Canonical directional-fairness audit

Both directions have 22 cases, 22 distinct expected source documents, 22 unique confusable sets, three confusable candidates per case, only normal/answerable cases, and the same category distribution: HR 2, operations 4, policy 6, security 6, support 2, technical 2. All 22 expected facts in each direction contain numeric/threshold content. Each direction has two policy-version source documents, and both corresponding queries reference the year. Each direction has exactly two queries with a literal number. Shared non-numeric surface terms between query and expected source occur in only 2/22 cases in either direction, with median overlap zero.

| Direction | Query chars median / p95 | Query words median | Source chars median / p95 | Source words median | Query-opening/template family |
| --- | ---: | ---: | ---: | ---: | --- |
| TR query → EN source | 82.5 / 90 | 11 | 141 / 165 | 21 | 20 nominal-clause openings; 2 year-context openings |
| EN query → TR source | 67 / 78 | 11 | 142.5 / 168 | 19 | 22 `what limit applies` openings |

Sources are similar in character length and the direction/category/numeric/policy/confusable counts are matched. The canonical set is nevertheless **not fully directionally matched**: Turkish queries are about 23% longer by median character count and use varied nominal constructions, while all English cross-language queries share one repeated opening template. Those are meaningful design differences and make the canonical directional gap less clean as a pure language-direction experiment. They do not account for the entire asymmetry, because the paired mirrored set also shows a gap.

## Mirrored-set findings

The 20 matched facts were evaluated with the same models and preprocessing. The expected source and opposite-language same-fact confusable were present for each query. These cases remain challenging even in the better direction, but the contrast is clear:

| Model | Direction | Rank buckets (1 / 2 / 3 / 4–5 / 6–10 / 11–20 / >20-or-miss) | Recall@3 | Recall@5 | Recall@10 | MRR@3 / @5 / @10 |
| --- | --- | --- | ---: | ---: | ---: | --- |
| MiniLM | TR → EN | 0 / 0 / 0 / 0 / 0 / 0 / 20 | 0.00 | 0.00 | 0.00 | 0.0000 / 0.0000 / 0.0000 |
| MiniLM | EN → TR | 0 / 0 / 0 / 1 / 1 / 4 / 14 | 0.00 | 0.05 | 0.10 | 0.0000 / 0.0125 / 0.0187 |
| E5-small | TR → EN | 0 / 4 / 2 / 1 / 2 / 10 / 1 | 0.30 | 0.35 | 0.45 | 0.1333 / 0.1433 / 0.1567 |
| E5-small | EN → TR | 0 / 9 / 1 / 6 / 2 / 2 / 0 | 0.50 | 0.80 | 0.90 | 0.2417 / 0.3067 / 0.3200 |

E5-small therefore retains a direction gap on a paired fact structure: Recall@10 is 0.45 TR→EN versus 0.90 EN→TR. The mirror is supplemental and only 20 facts; it cannot establish general language fairness, but it rejects the explanation that the canonical template imbalance alone caused the observed effect.

## Tokenization and truncation

Counts include model special tokens and the model-specific prefixes; document counts are the indexed chunks (one per document in both sets). p95 uses the nearest-rank percentile. All truncation counts are zero; the maximums are far below each model’s input limit (MiniLM 256, E5-small 512). E5 applies one `query: ` or `passage: ` prefix; no accidental double prefix was detected.

### Canonical corpus

| Model | Text | EN median / p95 / max (n) | TR median / p95 / max (n) | Truncated EN / TR |
| --- | --- | ---: | ---: | ---: |
| MiniLM | Queries | 15 / 22 / 23 (78) | 39 / 48 / 50 (78) | 0 / 0 |
| MiniLM | Documents | 29 / 38 / 38 (22) | 60.5 / 75 / 83 (22) | 0 / 0 |
| E5-small | Queries | 21 / 26 / 26 (78) | 23 / 27 / 29 (78) | 0 / 0 |
| E5-small | Documents | 35 / 44 / 46 (22) | 38 / 47 / 53 (22) | 0 / 0 |

### Mirrored diagnostic set

| Model | Text | EN median / p95 / max (n) | TR median / p95 / max (n) | Truncated EN / TR |
| --- | --- | ---: | ---: | ---: |
| MiniLM | Queries | 13.5 / 15 / 17 (20) | 27.5 / 34 / 37 (20) | 0 / 0 |
| MiniLM | Documents | 20 / 25 / 26 (20) | 42 / 49 / 49 (20) | 0 / 0 |
| E5-small | Queries | 17 / 21 / 21 (20) | 18.5 / 22 / 23 (20) | 0 / 0 |
| E5-small | Documents | 26 / 29 / 29 (20) | 27.5 / 33 / 33 (20) | 0 / 0 |

Tokenization length asymmetry is pronounced for MiniLM, especially Turkish query/document counts, but no input is near truncation. It cannot explain E5-small’s cross-language rank asymmetry via truncation. Unicode was verified in corpus tests and the preprocessor is prefix-only (no transliteration or normalization).

## Hard negatives and no-answer similarity

Expected correct-source recovery and confusable-source co-retrieval are separate outcomes:

| Model | Expected source in top 3 | Confusable present in top 3 | Cases with both | Expected above best confusable (among both) |
| --- | ---: | ---: | ---: | ---: |
| MiniLM | 40/44 | 17/44 cases; 17 source results | 17 | 13/17 (4 below) |
| E5-small | 44/44 | 20/44 cases; 21 source results | 20 | 19/20 (1 below) |

E5 improves expected-source hard-negative recovery to 44/44 and usually ranks it above the confusable, while still co-retrieving 21 designated confusable source results. The improved Hit@3 is not evidence that confusable material disappeared.

No-answer scores are diagnostic only; no threshold or refusal behavior was added. The tables show min / median / p95 / max. Each top-1 distribution has 132 answerable or 24 no-answer cases; the all-top-3 distributions contain 396 or 72 chunk scores respectively.

| Model | Set | Top-1 min / median / p95 / max | All top-3 min / median / p95 / max |
| --- | --- | --- | --- |
| MiniLM | Answerable | 0.2290 / 0.6897 / 0.8040 / 0.8669 | 0.2050 / 0.6458 / 0.7693 / 0.8669 |
| MiniLM | No-answer | 0.2686 / 0.5424 / 0.7417 / 0.7549 | 0.1630 / 0.4772 / 0.7297 / 0.7549 |
| E5-small | Answerable | 0.7983 / 0.8660 / 0.9293 / 0.9434 | 0.7771 / 0.8270 / 0.9186 / 0.9434 |
| E5-small | No-answer | 0.7790 / 0.8093 / 0.8782 / 0.8884 | 0.7580 / 0.8028 / 0.8560 / 0.8884 |

No-answer minus answerable top-1 median is −0.1473 for MiniLM and −0.0566 for E5-small; all-top-3 median difference is −0.1686 and −0.0242 respectively.

The distributions overlap, especially for E5-small. Similarity alone is not a safe answerability signal. Abstention remains a separate later product/evaluation milestone.

## Answers to the diagnostic questions

1. **Is E5-small genuinely weak in TR→EN on this workload?** Yes. Canonical top-10 recall is only 7/22, and the matched mirror preserves a substantial gap.
2. **Is the correct source usually just below K=3?** No. E5 has zero canonical cases at ranks 1–3, but only 7/22 at ranks 4–10; 15/22 are beyond rank 10 or absent from top 20. This is not mainly a small K=3 cutoff issue.
3. **Is the canonical corpus directionally biased?** It is imperfectly balanced in query form and length: all 22 English cases share one opening, while Turkish openings are varied and median query length is longer. Categories, source lengths, numeric facts, policy-version cases, and confusable counts are otherwise closely matched.
4. **Does the mirror reproduce the asymmetry?** Yes for E5-small (Recall@10 0.45 TR→EN vs 0.90 EN→TR); MiniLM performs poorly in both directions.
5. **Was an implementation bug found?** No. Prefixing, Unicode preservation, offline local model loading, finite unit-normalized vectors, cosine index semantics, and expected-source score agreement passed checks; no truncation occurred.
6. **Should E5-small remain under consideration?** It remains a useful experimental candidate: aggregate fixed-K retrieval, Turkish overall, EN→TR, and hard-negative recovery improved. It is not validated for the product because TR→EN remains a serious failure and no-answer score distributions overlap.
7. **Should E5-base be the next model?** It is the evidence-led next embedding candidate under classification B, but this task did not download or provision it. Evaluate it only in a later, explicitly provisioned offline paired run.
8. **Should reranking/candidate-pool be next instead?** Not as the primary next milestone: a top-10 reranker would have only 7/22 canonical TR→EN expected sources to reorder. A bounded top-20 reranker study can follow, but the evidence favors first testing whether a stronger embedding improves candidate recall.
9. **Should no-answer handling remain separate?** Yes. Keep abstention/refusal policy separate and do not derive a production threshold from these synthetic scores.

## Reproduction and limitations

The offline diagnostic runner is `app/tools/diagnose_cross_language_retrieval.py`; deterministic corpus inputs are under `evaluation/corpora/cross-language-mirror-v1/`. Focused regression coverage is in `tests/test_cross_language_diagnostics.py`. Full validation commands and results are recorded in the PR summary.

These small fictional corpora do not establish customer-document quality. The mirror is only 20 fact pairs, its questions are controlled synthetic prompts, and cosine score gaps are not calibrated probabilities. Existing performance estimates are retained from the paired benchmark rather than generalized from this diagnostic.
