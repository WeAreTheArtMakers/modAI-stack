# Local reranker v1 — blocked, not measured

## Status

The local reranker integration and its offline/error-path tests are implemented, but the model experiment was **not run**. A single pinned model download repeatedly stalled and failed with HTTPS read timeouts and proxy/CDN 502 responses. At the user's direction, the transfer was stopped with an incomplete cache of approximately 360 MB of the roughly 471 MB transfer; the partial cache remains outside the repository. No reranker quality or latency result is available.

## Candidate

- Model: [`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)
- Revision: `1427fd652930e4ba29e8149678df786c240d8825`
- Model card: approximately 0.1B parameters, Apache-2.0, and 15 listed languages. The card does not explicitly guarantee Turkish training/evaluation coverage; Turkish quality must be verified rather than assumed.
- Runtime constraints: local cache only, `local_files_only=True`, `trust_remote_code=False`, explicit failure when weights are unavailable, no silent fallback. Reranking is evaluation-only and disabled by default.

Candidate-pool sizes 6, 8, and 10 with final top-3 output remain unmeasured. The model cache is not included in Git. Resume only after the pinned files are fully available locally, then record quality, rank changes, hard-negative/no-answer behavior, and latency against the same private dataset fingerprint and embedding model.
