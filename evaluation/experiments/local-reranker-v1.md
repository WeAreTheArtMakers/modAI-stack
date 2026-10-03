# Local reranker v1 — BLOCKED BY MODEL PROVISIONING

## Status

The local reranker integration and its offline/error-path tests are implemented, but the model experiment was **not run**. A single pinned model download repeatedly stalled and failed with HTTPS read timeouts and proxy/CDN 502 responses. The transfer was stopped at the user's direction; a process check found no active download. The partial cache has been preserved. No reranker quality or latency result is available, and **no production reranker recommendation can be made until a compatible model is fully provisioned and evaluated**.

## Local cache audit

| Local cache entry | Inspection result | Reranker suitability |
| --- | --- | --- |
| `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`, revision `1427fd652930e4ba29e8149678df786c240d8825` | Partial cache at `~/.cache/huggingface/models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1`, also visible in the container at `/models/models--cross-encoder--mmarco-mMiniLMv2-L12-H384-v1`. Config/tokenizer files exist, but the model-weight blob is `5daeca2481a76b5976a2bdc32f0a78532b6716da4f8cd3ff59460ef8d2f359b4.incomplete` (398,458,880 bytes); there is no complete weight link in the pinned snapshot. | Intended cross-encoder, but **not loadable offline**. Do not run the experiment until provisioning completes. The incomplete cache was not deleted. |
| `sentence-transformers/all-MiniLM-L6-v2` | Present in the Hugging Face hub cache. Its SentenceTransformers modules are `Transformer → Pooling → Normalize`. | Embedding bi-encoder already used for retrieval, not a query/passage cross-encoder reranker; explicitly excluded. |
| `bert-base-uncased`, `roberta-base`, `google/electra-small-discriminator` | Cached architectures are respectively `BertForMaskedLM`, `RobertaForMaskedLM`, and `ElectraForPreTraining`. | Base/pretraining checkpoints, not fine-tuned relevance cross-encoders; excluded rather than repurposed. |
| Project `./models` directory and legacy SentenceTransformers cache locations | Project `./models` is empty; `~/.cache/torch/sentence_transformers` and `~/.cache/sentence_transformers` have no cached model files. The API container's `/models` mount is backed by `~/.cache/huggingface`. | No additional usable reranker found. |
| `modAIJet:latest` and other local generative checkpoints | Generation models, not a pairwise relevance model. | Explicitly excluded; no Ollama LLM substitution was made. |

No complete compatible cross-encoder/reranker was found in the inspected Hugging Face hub, SentenceTransformers, project, or mounted model caches.

## Intended candidate and runtime

- Candidate: [`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1`](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1), pinned at `1427fd652930e4ba29e8149678df786c240d8825`.
- License: Apache-2.0 per the [model card](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1). It lists 15 languages but does not explicitly guarantee Turkish training/evaluation coverage; Turkish quality must be measured, not assumed.
- Intended inference backend: `sentence_transformers.CrossEncoder` using its default PyTorch inference path. Inference was **not** initialized or run because the checkpoint is incomplete.
- The evaluation loader enforces `local_files_only=True`, `trust_remote_code=False`, and an explicit error if weights are unavailable; no silent fallback occurs. Reranking remains evaluation-only and disabled by default.

Candidate-pool sizes 6, 8, and 10 with final top-3 output remain unmeasured. No model files or partial weights are included in Git. Resume only after the pinned files are fully available locally, then record quality, rank changes, hard-negative/no-answer behavior, and latency against the same private dataset fingerprint and embedding model. Until then, production stays at `RAG_TOP_K=3` with no reranker recommendation.
