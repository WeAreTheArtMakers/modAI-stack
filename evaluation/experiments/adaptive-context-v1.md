# Adaptive Context Selection v1

Date: 2026-10-03
Run type: Local, authorized retrieval experiment; generation confirmation for the leading in-sample rule

## Scope and reproducibility

- Cases: 24
- Dataset fingerprint: `41be34dd1a014ad6f7bfc97218c763277952a228487dfd418dd5ea76b5a18bcc`
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Generation model: local Ollama `modAIJet:latest`
- Retrieval fetched the normal top three results for every case. Candidate selection ran only in the evaluation retriever; production remains fixed at `RAG_TOP_K=3`.
- The six generation runs alternated `fixed K=3`, `adaptive gap`, `adaptive gap`, `fixed K=3`, `fixed K=3`, `adaptive gap`.
- No questions, prompts, source text, or full generated answers are included here. Evaluation output stores only numeric score metadata and generated-answer character counts.

## Qdrant score semantics

The current collection is created with `Distance.COSINE`; `QdrantService.search` returns Qdrant's `ScoredPoint.score`. For cosine similarity, higher scores rank as more similar; cosine is mathematically in `[-1, 1]`. Qdrant implements cosine search by normalizing vectors and using dot product. See [Qdrant's collection metric documentation](https://qdrant.tech/documentation/manage-data/collections/) and [overview of similarity metrics](https://qdrant.tech/documentation/overview/what-is-qdrant/).

The 24 observed cases had top-one scores `0.384649–0.814240`, top-two `0.161291–0.703184`, and top-three `0.143979–0.612743`. These are corpus observations, not calibrated confidence values. Their scale and distribution are not established as comparable across queries, so the candidates below use within-query gaps or ratios.

## Fixed K=3 baseline

| Hit@K | MRR | Source accuracy | Fact coverage | Mean/median sources |
|------:|----:|----------------:|--------------:|-------------------:|
| 1.000000 | 0.930556 | 0.333333 | 1.000000 | 3 / 3 |

Expected-source rank distribution:

| Rank 1 | Rank 2 | Rank 3 | Not found |
|-------:|-------:|-------:|----------:|
| 21 | 2 | 1 | 0 |

One case in the `general` category requires the third result: K=2 misses its expected source and drops fact coverage. No question text or case identifier is disclosed.

That case's score gap `score_gap_2_3` is `0.01735881` and ratio `score3/score2` is `0.96549016`. The gap is relatively small compared with the all-case median `0.04666743`, and the ratio is high compared with its median `0.89045031`. Neither signature uniquely separates it: some other cases have a smaller gap, while non-required cases reach ratio `0.99791517`.

## Candidate policies

- **A — gap:** return two by default; return three when `score2 - score3 <= threshold`.
- **B — ratio:** return two by default; return three when `score3 / score2 >= threshold`. Ratios are undefined when the denominator is non-positive.
- **C — three-tier:** return one when `score1 - score2` exceeds a threshold; otherwise return three when `score2 - score3` is at or below its threshold; return two in other cases.

Thresholds were swept on this dataset only. Policy A had 48 tested threshold points with both Hit@K and fact coverage preserved and mean context below three. The lowest passing threshold was `0.01735881`; its decision pattern remains unchanged until the next score-gap breakpoint, `0.02140478` (upper endpoint excluded). Policy B had 47 tested points; even its most selective quality-preserving result removed only one third result. Policy C had 1,364 tested threshold pairs; its best in-sample point was gap23 `0.01735881`, gap12 `0.077319085`.

## Retrieval comparison

| Configuration | Hit@K | MRR | Source accuracy | Fact coverage | Mean sources | Median | 1 source | 2 sources | 3 sources |
|---|------:|----:|----------------:|--------------:|-------------:|-------:|----------:|----------:|----------:|
| Fixed K=3 | 1.000000 | 0.930556 | 0.333333 | 1.000000 | 3.000 | 3 | 0 | 0 | 24 |
| A, gap `0.01735881` | 1.000000 | 0.930556 | 0.452830 | 1.000000 | 2.208 | 2 | 0 | 19 | 5 |
| B, ratio `0.96549016` | 1.000000 | 0.930556 | 0.338028 | 1.000000 | 2.958 | 3 | 0 | 1 | 23 |
| C, gap23 `0.01735881`, gap12 `0.077319085` | 1.000000 | 0.930556 | 0.727273 | 1.000000 | 1.375 | 1 | 17 | 5 | 2 |

Policy A returns two sources for 19 cases and three for five. Of those five three-source decisions, one is required by observed labels; four are conservative extra results. Policy C can return one source for 17 cases in-sample, but it is more aggressive and has the same validation weakness described below.

## Holdout and sensitivity

For each category holdout, the threshold was selected using the remaining categories and evaluated on the held-out cases. Gap A preserved both required quality metrics in 4 of 5 folds. The fold holding out `general` fell to Hit@K `0.666667` and fact coverage `0.666667`, because that fold contains the only observed case requiring rank three. Policy B and C also passed 4 of 5 category folds.

Leave-one-case-out recalibration passed 23 of 24 cases for A, B, and C. Omitting the single rank-three-required case from calibration causes the selected rule to fall back to two results and fail on that omitted case. The threshold's lower bound is therefore determined by one example, rather than a repeated pattern across independent cases.

This is a direct sign of fragility, even though the in-sample gap threshold has a small plateau and the wider scanned interval preserves aggregate metrics. It is not evidence that the rule generalizes to another corpus.

## Generation confirmation — policy A

Each row reports the median of the three run-level case medians, followed by the min–max across those three runs. Answer size is character count; answer text was not persisted.

| Configuration | Groundedness | Generation ms | Total ms | Median source count | Answer chars |
|---|---:|---:|---:|---:|---:|
| Fixed K=3 | 1.000000 (0.958333–1.000000) | 7647.422 (6057.876–8405.575) | 7757.058 (6166.863–8558.194) | 3 | 67 |
| Adaptive gap A | 1.000000 (0.916667–1.000000) | 6799.582 (6283.506–8070.684) | 6921.851 (6368.814–8213.045) | 2 | 64 |

Adaptive A's median generation and total times were about 11.1% and 10.8% lower, respectively, in these three alternating runs. The ranges overlap, and one adaptive run had lower groundedness (`0.916667`) than any fixed-K=3 run. Output length was also slightly lower, so the latency difference cannot be attributed solely to fewer context chunks.

## Conclusion and limitations

On this corpus, adaptive selection can reduce average context below three while preserving retrieval Hit@K, MRR, and fact coverage. Gap A is the clearest two-or-three-source rule, averaging `2.208` sources; the ratio rule barely reduces context. A three-tier rule reaches `1.375` sources in-sample but is especially aggressive.

No rule is stable enough for production confirmation yet. The single rank-three-required case determines whether the policy keeps three results, category holdout fails when that case's category is excluded, and a generation repetition showed lower groundedness. The corpus has only 24 cases and one rank-three-required example. The next useful experiment needs additional independently authored cases, especially cases whose evidence ranks third, before selecting or confirming a production threshold.

Production behavior and `.env.example` remain `RAG_TOP_K=3`; adaptive selection is evaluation-only.
