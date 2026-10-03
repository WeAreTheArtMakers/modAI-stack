# Retrieval robustness v1 — aggregate results

## Scope

- Private, synthetic, locally generated corpus; no raw corpus, questions, answers, prompts, document names/IDs, or per-case results are committed.
- 92 cases: 55 normal, 20 hard-negative, 15 no-answer, and 2 cross-organization access probes.
- Languages: 55 English and 37 Turkish. Categories: general 4, HR 20, operations 24, policy 2, security 27, support 4, and technical 11.
- 75 answerable cases cover two expected facts each. The set includes 20 near-duplicate scenario groups and 35 cases with confusable labels.
- Dataset fingerprint (SHA-256): `009f231b51d3b7004fcf7116c9c2f3f248d351d3d2ae4e67d97ca73b170f58cc`.
- Retrieval used the locally cached `sentence-transformers/all-MiniLM-L6-v2` embeddings and an isolated temporary Qdrant collection. No LLM generation or judge was used. Fixed baseline and final output size were K=3.

## Fixed K=3 baseline

| Metric | Result |
| --- | ---: |
| Answerable Hit@3 | 73/75 (97.33%) |
| Mean reciprocal rank | 93.33% |
| Fact coverage | 97.33% |
| Source accuracy | 32.44% |
| Median embedding latency | 24.06 ms |
| Median retrieval latency | 43.27 ms |
| Median total latency | 68.57 ms |

Expected answer-source rank across the 75 answerable cases: rank 1, 67; rank 2, 6; rank 3, 0; missed by K=3, 2. Fifteen cases were explicitly no-answer and two were access probes, so they are not included in the answerable rank denominator.

The no-answer cases produced a confusable retrieval in 14/15 cases. This is a retrieval signal only; no refusal or generated-answer quality was measured. Source accuracy is low in this synthetic corpus and should be interpreted alongside the curated expected-source set, not as a semantic answer-quality score.

Both cross-organization requests were denied (2/2). A direct tenant-filter probe found zero foreign-scope vector leaks. Temporary benchmark database rows and the isolated Qdrant collection were removed after the run.

## Adaptive context selection

Scenario groups were split deterministically before calibration; no scenario group crossed the calibration/holdout boundary. The answerable calibration set contained 58 cases and the answerable holdout contained 17. Thresholds were selected only on calibration data.

All three candidates (gap, ratio, and three-tier) retained calibration Hit@3, MRR, and fact coverage at 100%. On holdout, each scored 15/17 (88.24%) for Hit@3, MRR, and fact coverage, versus 17/17 (100%) for the fixed-K=3 baseline. The candidates therefore fail the holdout-preservation criterion and are rejected; none is recommended for production.

## Limitations

This is a small synthetic, local benchmark, not a customer-data or production workload evaluation. Timing is a single local run and is hardware/service dependent. No LLM answer generation, refusal behavior, or semantic judge was evaluated. Production configuration remains unchanged at `RAG_TOP_K=3`.
