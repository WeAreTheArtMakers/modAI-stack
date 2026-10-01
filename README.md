# modAI-stack

<p align="center">
  <img src="assets/modai-stack-logo.png" alt="modAI-stack logo" width="760">
</p>

> Yerel çalışan LLM’ler, gerçek zamanlı sohbet, RAG ve vektör aramayı tek bir modüler platformda birleştiren yapay zekâ uygulama altyapısı.

[GitHub deposu](https://github.com/WeAreTheArtMakers/modAI-stack)

## Kısa açıklama

modAI-stack; Ollama ile yerel model çalıştırmayı, FastAPI tabanlı asenkron API’yi, WebSocket üzerinden token akışını, belge yükleme ve RAG sorgularını bir araya getirir. Uygulama; PostgreSQL ile kalıcı verileri, Qdrant ile anlamsal aramayı, Redis ile geçici iş/rate-limit durumunu kullanır. LLM sağlayıcısı soyutlandığı için ileride Ollama yerine vLLM eklemek API ve iş mantığını değiştirmeden mümkündür.

## Kullanılan teknolojiler

| Katman | Teknolojiler |
| --- | --- |
| Backend API | Python 3.11+, FastAPI, Pydantic, Uvicorn |
| Asenkron çalışma | `asyncio`, bounded job queue, worker cancellation, timeout ve backpressure |
| LLM serving | Ollama, provider abstraction; vLLM için genişletilebilir yapı |
| RAG | Sentence Transformers embeddings, configurable chunking, güvenli context construction |
| Vector database | Qdrant, cosine similarity, metadata filtering |
| Relational database | PostgreSQL, SQLAlchemy async ORM, asyncpg |
| Cache / coordination | Redis |
| Gerçek zamanlı iletişim | WebSockets, token streaming, connection isolation |
| Kimlik ve güvenlik | JWT, access/refresh token, bcrypt password hashing, RBAC, input validation |
| Doküman işleme | PDF (`pypdf`), Markdown, TXT; dosya boyutu ve uzantı doğrulama |
| Model adaptation | Hugging Face Transformers, Datasets, PEFT / LoRA |
| Altyapı | Docker, Docker Compose, persistent volumes, health/readiness checks |
| Test | pytest, pytest-asyncio, httpx |

---

# Local AI Realtime RAG Platform

Local-first interview project demonstrating an async FastAPI backend around Ollama, PostgreSQL, Redis, Qdrant, JWT, WebSockets, document ingestion, and PEFT/LoRA.

## Architecture

```text
Client -> FastAPI REST/WebSocket -> auth + bounded jobs -> provider interface -> Ollama
                                      |                         |
                               PostgreSQL                  RAG pipeline -> Qdrant
                                      Redis (job state/rate limiting)
```

The application never calls Ollama outside `app/services/llm`; replacing it with a `VLLMProvider` preserves API and RAG business logic. Qdrant is similarly isolated. Retrieved text is explicitly labeled untrusted in the prompt and cannot override system instructions.

## Run locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
ollama pull llama3.2:3b
uvicorn app.main:app --reload
```

For infrastructure, `docker compose up --build` starts API, PostgreSQL, Redis, and Qdrant. Ollama can remain on the host; set `OLLAMA_BASE_URL=http://host.docker.internal:11434` in Docker environments. Add real secrets only to `.env`, never source control.

## API examples

```bash
curl -X POST localhost:8000/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"user@example.com","password":"correct-horse-battery"}'
curl -X POST localhost:8000/chat -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"prompt":"Explain embeddings"}'
curl -X POST localhost:8000/documents/upload -H "Authorization: Bearer $TOKEN" -F file=@notes.pdf
curl -X POST localhost:8000/rag/query -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"question":"What does the document say?"}'
```

Connect to `ws://localhost:8000/ws/chat?token=<access-token>` and send a text prompt. The server emits `{type: "token"}` messages followed by `{type: "complete"}`. Disconnects and provider failures are contained per connection.

## Design notes

Async I/O keeps database, network, and streaming operations from blocking other requests. Timeouts, bounded queues, semaphores, and cancellation are the controls needed for backpressure and concurrency; Redis is the intended shared store for rate limits and transient job state, while PostgreSQL remains the source of truth. Qdrant provides cosine similarity search and metadata filtering without coupling retrieval to SQL. In production, add Alembic migrations, distributed rate limiting, structured JSON logs/metrics, object storage for originals, and separate worker deployment.

The current upload route persists extracted text and the RAG endpoint demonstrates the safe prompt boundary; production wiring should add the embedding model, Qdrant collection/upsert/delete operations, and background ingestion job using `JobQueue`.

## Testing and training

```bash
pytest
python training/train_lora.py
```

LoRA is adapter training, not an Ollama Modelfile. Prompt/system settings alter inference instructions; RAG injects query-time knowledge; LoRA learns adapter parameters; full fine-tuning updates all model weights. See `training/README.md`.

## Technical Interview Discussion

1. RAG is preferable for changing/private documents because knowledge can be updated without retraining.
2. A Modelfile configures serving/prompt behavior; LoRA changes learned adapter weights.
3. `asyncio` overlaps network waits and streams tokens efficiently.
4. Blocking inference must move behind an async client or worker/process; otherwise the event loop stalls every request.
5. WebSockets provide low-latency bidirectional token streaming.
6. Use connection limits, bounded queues, per-request cancellation, horizontal workers, and a distributed rate limiter.
7. Route requests across model replicas/GPUs and batch where the serving engine supports it.
8. Implement `VLLMProvider` against the same `LLMProvider` contract.
9. Backpressure occurs at WebSocket send buffers, bounded job queues, model concurrency, and Qdrant/database pools.
10. Treat retrieved content as untrusted and separate it from system instructions, as the pipeline does.
11. Qdrant is purpose-built for vector search, payload filters, and operational persistence.
12. Inspect chunking, embedding model, top-k, score distribution, and a labeled retrieval evaluation set.
13. Fail gracefully, expose readiness failure, retry boundedly, and use cached/queued work where appropriate.
14. Return a safe provider-unavailable error and keep health/readiness distinct from API liveness.
15. Estimate parameter memory plus KV cache, activations, and runtime overhead; validate empirically with the target quantization.
16. Authentication establishes identity; authorization checks role/resource permissions.
17. Redis holds ephemeral coordination/rate state; PostgreSQL stores durable users, documents, sessions, and messages.
18. Validate inputs, enforce upload limits, expire JWTs, rate-limit expensive endpoints, and avoid leaking errors.
19. Emit request ID, endpoint, status, retrieval latency, LLM latency, and token/queue metrics without sensitive content.
20. Add migrations, secrets management, TLS, object storage, observability, autoscaling workers, backups, and failure drills.
