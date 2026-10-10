# Third-Party Notices

modAI-stack uses third-party open-source software distributed under their own
licenses.

The WATAM Source-Available License (see `LICENSE`) that governs modAI-stack does not replace,
restrict, or modify the licenses of third-party dependencies.

Third-party components remain subject to their respective license terms.

Major dependency families currently include software distributed under
permissive licenses such as:

- Apache License 2.0
- MIT License
- BSD licenses
- ISC License
- Mozilla Public License 2.0
- Python Software Foundation License
- Boost Software License 1.0

Dependency license inventories should be regenerated for each production
release and reviewed before redistribution.

Model weights are not automatically licensed under the modAI-stack license.
Each model remains subject to the license or terms provided by its respective
publisher.

## Release notice requirement

This document summarizes the major third-party license families currently
observed in the project. It is not intended to replace an exact release-time
dependency inventory.

Before redistributing a production release, the dependency inventory must be
regenerated and any copyright notices, license texts, attribution requirements,
or other obligations required by redistributed third-party components must be
included with that release.

## modAI Voice browser components

The voice assistant downloads these components from the application's own origin;
they are not part of the Git repository except where noted.

| Component | Version | License | Notes |
|---|---|---|---|
| Transformers.js (`@huggingface/transformers`) | 4.3.0 | Apache-2.0 | npm dependency, bundled into the voice worker |
| ONNX Runtime Web (`onnxruntime-web`) | 1.30.0 | MIT | npm dependency; WebAssembly runtime bundled as an asset |
| Whisper tiny ONNX (`Xenova/whisper-tiny`, from `openai/whisper-tiny`) | revision 5332fcc35e32a33b86612b9a57a89be7906102b1 | Apache-2.0 (model card) | downloaded by `scripts/fetch_voice_models.py` |
| Whisper base ONNX (`Xenova/whisper-base`, from `openai/whisper-base`), optional | revision 64da57285918e20ea79ea5c88eed7197933abaa8 | Apache-2.0 (model card) | downloaded only with `scripts/fetch_voice_models.py --include-optional` |
| EMA Lightning ONNX (`ozcancelik/ema-lightning-onnx`, from `canberkkkkkk/ema-lightning`) | revision 13c431db0356b2f7fafb1247cd823ec0d777c820 | Apache-2.0 | downloaded by `scripts/fetch_voice_models.py`; LICENSE and NOTICE in `frontend/public/third-party/ema-lightning-onnx/` |
| normalizer-tr (inside EMA's `normalizer.wasm`) | commit d0bc1bc6523faa4f6257642190bb723b7f4274a5 | Apache-2.0 | Rust dependency notices in `frontend/public/third-party/ema-lightning-onnx/normalizer-tr-THIRD_PARTY_NOTICES.md` |
| EMA Lightning JavaScript engine (`web/tts.js`, `web/normalizer.js`) | same revision | Apache-2.0 | ported to TypeScript with modifications in `frontend/src/voice/vendor/emaLightning.ts` |

## Server-side models and services

Model weights and container images are not part of the Git repository. Each is obtained by the
installer from its publisher, under that publisher's terms.

| Component | Version | License or terms | How it is obtained |
|---|---|---|---|
| BGE-M3 (`BAAI/bge-m3`), multilingual retrieval profile | revision 31e47391fcbda65be526abe98e646b3c6cd845a8 | MIT (model card) | `scripts/fetch_retrieval_models.py`, verified against `retrieval-models.lock.json` |
| all-MiniLM-L6-v2 (`sentence-transformers/all-MiniLM-L6-v2`), legacy retrieval profile | Hugging Face cache | Apache-2.0 (model card) | `python -m app.tools.prefetch_embedding_model` |
| Generation model served by Ollama (default `gemma3:4b` / `modAIJet:latest`) | as pulled | the model publisher's terms (Gemma models: Gemma Terms of Use and Prohibited Use Policy) | `ollama pull` by the operator |
| Ollama | host installation | MIT | installed by the operator |
| Qdrant (`qdrant/qdrant`) | v1.12.5 | Apache-2.0 | Docker image |
| PostgreSQL (`postgres`) | 16 | PostgreSQL License | Docker image |
| Valkey (`valkey/valkey`), Redis-protocol compatible queue and cache | 8.1 (8.1.10 verified October 2026) | BSD-3-Clause | Docker image |

Release review items:
- **Redis replaced by Valkey:** Redis 7.4 and later are licensed under RSALv2/SSPLv1 (Redis 8 adds AGPLv3), which are not permissive and are routinely flagged by customer legal reviews. Releases from v0.6.1 use Valkey (BSD-3-Clause), a Linux Foundation fork that speaks the same protocol; no application change is needed. See `docs/guides/lisanslama.md`.
- **Gemma models:** if a release ships or pre-installs Gemma weights, the Gemma Terms of Use must accompany them and the use restrictions passed on to the customer.
- This table is a summary for review. It is not legal advice and does not replace the release-time dependency inventory described above.
