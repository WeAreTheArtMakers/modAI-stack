"""Offline retrieval experiment orchestration over an in-memory Qdrant index."""

from __future__ import annotations

import asyncio
import hashlib
import math
import platform
import time
from collections.abc import Sequence
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid4, uuid5

from qdrant_client import QdrantClient, models

from app.services.rag.chunker import chunk_text
from app.services.rag.embeddings import EmbeddingService
from benchmarks.retrieval.metrics import QueryOutcome, aggregate_metrics
from benchmarks.retrieval.provenance import validate_source_provenance
from benchmarks.retrieval.safety import (
    BenchmarkSafetyError,
    assert_endpoint_isolated,
    create_owned_collection,
)
from benchmarks.retrieval.schema import BenchmarkDataset, dataset_fingerprint


@dataclass(frozen=True)
class BenchmarkChunk:
    document_id: str
    chunk_id: str
    chunk_index: int
    language: str
    text: str


class DeterministicFixtureEmbedder:
    """Small hash-vector stub for plumbing checks; never represents model quality."""

    dimension = 128

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    @classmethod
    def _vector(cls, text: str) -> list[float]:
        vector = [0.0] * cls.dimension
        for token in text.casefold().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % cls.dimension
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0
        return [value / norm for value in vector]


@dataclass(frozen=True)
class RunConfiguration:
    dataset: BenchmarkDataset
    embedding_model: str
    embedding_revision: str
    embedding_dimension: int
    query_prefix: str
    passage_prefix: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    execution_mode: str
    device: str
    source_sha: str | None
    source_sha_origin: str
    model_load_ms: float | None = None
    runtime_build_sha: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dataset, BenchmarkDataset):
            raise TypeError("the retrieval runner only accepts schema v1 datasets; v2 support is deferred to P1-B")
        validate_source_provenance(self.source_sha, self.source_sha_origin)


def _build_chunks(dataset: BenchmarkDataset, *, chunk_size: int, chunk_overlap: int) -> list[BenchmarkChunk]:
    chunks: list[BenchmarkChunk] = []
    for document in dataset.documents:
        for index, text in enumerate(chunk_text(document.text, chunk_size, chunk_overlap)):
            chunks.append(
                BenchmarkChunk(
                    document_id=document.document_id,
                    chunk_id=f"{document.document_id}::chunk-{index:04d}",
                    chunk_index=index,
                    language=document.language,
                    text=text,
                )
            )
    if not chunks:
        raise ValueError("benchmark dataset produced no chunks")
    return chunks


def _validate_vectors(vectors: Sequence[Sequence[float]], *, expected_count: int, dimension: int | None = None) -> int:
    if len(vectors) != expected_count:
        raise ValueError("embedding model returned an unexpected vector count")
    if not vectors:
        raise ValueError("embedding model returned no vectors")
    actual_dimension = len(vectors[0])
    if actual_dimension <= 0 or (dimension is not None and actual_dimension != dimension):
        raise ValueError("embedding model returned an unexpected vector dimension")
    for vector in vectors:
        if len(vector) != actual_dimension or any(not math.isfinite(float(value)) for value in vector):
            raise ValueError("embedding vectors must be finite and dimensionally consistent")
        norm = math.sqrt(sum(float(value) ** 2 for value in vector))
        if not math.isclose(norm, 1.0, rel_tol=1e-4, abs_tol=1e-4):
            raise ValueError("embedding vectors must be normalized as in production")
    return actual_dimension


def _retrieved_document_order(
    hits,
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    document_ids: list[str] = []
    chunk_ids: list[str] = []
    chunk_document_ids: list[str] = []
    for hit in hits:
        payload = hit.payload or {}
        document_id = payload.get("benchmark_document_id")
        chunk_id = payload.get("benchmark_chunk_id")
        if isinstance(document_id, str) and document_id not in document_ids:
            document_ids.append(document_id)
        if isinstance(chunk_id, str):
            chunk_ids.append(chunk_id)
            chunk_document_ids.append(document_id if isinstance(document_id, str) else "")
    return tuple(document_ids), tuple(chunk_ids), tuple(chunk_document_ids)


def _make_client(
    *, benchmark_endpoint: str | None = None, production_endpoint: str | None = None
) -> QdrantClient:
    """Use Qdrant's in-process local backend; never read QDRANT_URL or connect."""
    if benchmark_endpoint is not None:
        if production_endpoint is None:
            raise BenchmarkSafetyError("remote Qdrant selection requires an explicit production endpoint comparison")
        assert_endpoint_isolated(benchmark_endpoint, production_endpoint)
        raise BenchmarkSafetyError("remote Qdrant endpoints are unsupported; use the isolated in-memory backend")
    if production_endpoint is not None:
        raise BenchmarkSafetyError("production endpoint is not a benchmark target")
    return QdrantClient(":memory:")


async def run_benchmark(config: RunConfiguration, embedder) -> dict:
    """Run retrieval only; no DB, production service, endpoint, or LLM is involved."""
    if config.top_k <= 0:
        raise ValueError("top_k must be positive")
    chunks = _build_chunks(
        config.dataset,
        chunk_size=config.chunk_size,
        chunk_overlap=config.chunk_overlap,
    )
    known_chunks = {chunk.chunk_id for chunk in chunks}
    for query in config.dataset.queries:
        if not set(query.expected_chunk_ids).issubset(known_chunks):
            raise ValueError(
                f"query {query.query_id} has chunk labels incompatible with the selected chunk size/overlap"
            )

    document_started = time.perf_counter()
    document_vectors = await embedder.embed_texts(
        [config.passage_prefix + chunk.text for chunk in chunks]
    )
    embedding_dimension = _validate_vectors(
        document_vectors,
        expected_count=len(chunks),
        dimension=config.embedding_dimension,
    )
    document_embedding_ms = (time.perf_counter() - document_started) * 1000

    client = _make_client()
    run_id = uuid4().hex
    collection_name = f"modai_benchmark_{run_id}"
    lease = None
    outcomes: list[QueryOutcome] = []
    top_k = max(5, config.top_k)
    try:
        lease = create_owned_collection(client, name=collection_name, dimensions=embedding_dimension)
        points = [
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"retrieval-benchmark-v1:{config.dataset.dataset_version}:{chunk.chunk_id}")),
                vector=list(vector),
                payload={
                    "benchmark_version": config.dataset.dataset_version,
                    "benchmark_document_id": chunk.document_id,
                    "benchmark_chunk_id": chunk.chunk_id,
                    "chunk_index": chunk.chunk_index,
                    "language": chunk.language,
                    "filename": f"{chunk.document_id}.fixture",
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, document_vectors, strict=True)
        ]
        client.upsert(collection_name=collection_name, points=points, wait=True)

        for query in config.dataset.queries:
            embedding_started = time.perf_counter()
            query_vectors = await embedder.embed_texts([config.query_prefix + query.question])
            _validate_vectors(query_vectors, expected_count=1, dimension=embedding_dimension)
            embedding_ms = (time.perf_counter() - embedding_started) * 1000

            retrieval_started = time.perf_counter()
            hits = client.search(
                collection_name=collection_name,
                query_vector=list(query_vectors[0]),
                limit=top_k,
                with_payload=True,
            )
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            retrieved_documents, retrieved_chunks, chunk_document_ids = _retrieved_document_order(hits)
            outcomes.append(
                QueryOutcome(
                    query_id=query.query_id,
                    language=query.language,
                    categories=tuple(query.categories),
                    answerable=query.answerable,
                    expected_document_ids=tuple(query.expected_document_ids),
                    expected_chunk_ids=tuple(query.expected_chunk_ids),
                    retrieved_document_ids=retrieved_documents,
                    retrieved_chunk_ids=retrieved_chunks,
                    top_score=float(hits[0].score) if hits else None,
                    embedding_latency_ms=embedding_ms,
                    retrieval_latency_ms=retrieval_ms,
                    retrieved_chunk_document_ids=chunk_document_ids,
                )
            )

        case_records = []
        for outcome in outcomes:
            case_records.append(
                {
                    "query_id": outcome.query_id,
                    "language": outcome.language,
                    "categories": list(outcome.categories),
                    "answerable": outcome.answerable,
                    "expected_document_ids": list(outcome.expected_document_ids),
                    "expected_chunk_ids": list(outcome.expected_chunk_ids),
                    "retrieved_document_ids": list(outcome.retrieved_document_ids),
                    "retrieved_chunk_ids": list(outcome.retrieved_chunk_ids),
                    "retrieved_chunk_document_ids": list(outcome.retrieved_chunk_document_ids),
                    "top_score": outcome.top_score,
                    "embedding_latency_ms": round(outcome.embedding_latency_ms, 3),
                    "retrieval_latency_ms": round(outcome.retrieval_latency_ms, 3),
                }
            )

        language_counts = {
            language: sum(query.language == language for query in config.dataset.queries)
            for language in ("tr", "en", "mixed")
        }
        category_counts = {
            category: sum(category in query.categories for query in config.dataset.queries)
            for category in (
                "single_document_fact",
                "multi_document",
                "long_document",
                "semantic_distractors",
                "unanswerable",
            )
        }
        return {
            "schema_version": 2,
            "classification": (
                "Fixture / engineering validation baseline"
                if config.dataset.classification == "fixture"
                else "Authoritative real-world evaluation corpus (operator-declared)"
            ),
            "real_world_benchmark_status": (
                "ESTABLISHED"
                if (
                    config.dataset.classification == "authoritative"
                    and config.execution_mode == "offline local model inference"
                )
                else "NOT YET ESTABLISHED"
            ),
            "metadata": {
                "dataset_name": config.dataset.name,
                "dataset_version": config.dataset.dataset_version,
                "dataset_sha256": dataset_fingerprint(config.dataset),
                "dataset_classification": config.dataset.classification,
                "authoritative_corpus_operator_confirmed": config.dataset.classification == "authoritative",
                "source_sha": config.source_sha,
                "source_sha_origin": config.source_sha_origin,
                "runtime_build_sha": config.runtime_build_sha,
                "embedding_model": config.embedding_model,
                "embedding_revision": config.embedding_revision,
                "embedding_dimension": embedding_dimension,
                "query_prefix": config.query_prefix,
                "passage_prefix": config.passage_prefix,
                "device": config.device,
                "distance_metric": "cosine",
                "normalization": "unit-normalized embeddings, matching production EmbeddingService",
                "chunker": "app.services.rag.chunker.chunk_text",
                "chunk_size": config.chunk_size,
                "chunk_overlap": config.chunk_overlap,
                "requested_top_k": config.top_k,
                "retrieval_limit": top_k,
                "document_count": len(config.dataset.documents),
                "chunk_count": len(chunks),
                "query_count": len(config.dataset.queries),
                "language_counts": language_counts,
                "category_counts": category_counts,
                "execution_mode": config.execution_mode,
                "qdrant_isolation_mode": "local in-memory QdrantClient (:memory:); no network endpoint",
                "collection_name_prefix": "modai_benchmark_",
                "model_load_ms": round(config.model_load_ms, 3) if config.model_load_ms is not None else None,
                "document_embedding_ms": round(document_embedding_ms, 3),
                "python_version": platform.python_version(),
                "platform": platform.platform(),
            },
            "metric_semantics": {
                "recall_at_k": "macro average per answerable query: relevant labeled documents represented by the first K Qdrant chunk results divided by all relevant documents",
                "hit_at_k": "fraction of answerable queries with at least one relevant document represented by the first K Qdrant chunk results; this is the document/source hit rate",
                "mrr_at_k": "mean reciprocal rank of first relevant distinct document within K; misses score zero",
                "source_precision_at_k": "relevant distinct documents divided by all distinct returned documents across answerable queries",
                "chunk_recall_at_k": "macro average only over queries with explicit expected chunk IDs",
                "unanswerable": "candidate return rate and mean top score describe retrieval only, not answerability classification",
                "category_aggregation": "multi-category queries appear once in each matching subgroup; global aggregates count each query once",
            },
            "metrics": aggregate_metrics(outcomes),
            "cases": case_records,
        }
    finally:
        try:
            if lease is not None and lease.created_by_run:
                lease.delete()
        finally:
            client.close()


def run_benchmark_sync(config: RunConfiguration, embedder) -> dict:
    return asyncio.run(run_benchmark(config, embedder))
