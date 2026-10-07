"""Deterministic document/chunk retrieval metrics and subgroup aggregation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Sequence


@dataclass(frozen=True)
class QueryOutcome:
    query_id: str
    language: str
    categories: tuple[str, ...]
    answerable: bool
    expected_document_ids: tuple[str, ...]
    expected_chunk_ids: tuple[str, ...]
    retrieved_document_ids: tuple[str, ...]
    retrieved_chunk_ids: tuple[str, ...]
    top_score: float | None
    embedding_latency_ms: float
    retrieval_latency_ms: float
    retrieved_chunk_document_ids: tuple[str, ...] = ()


def _documents_at_chunk_cutoff(result: QueryOutcome, k: int) -> tuple[str, ...]:
    """Deduplicate sources represented by Qdrant's first K chunk results."""
    if result.retrieved_chunk_document_ids:
        return tuple(dict.fromkeys(result.retrieved_chunk_document_ids[:k]))
    # Keep pure metric tests and hand-authored observations ergonomic when only
    # document rankings are supplied.
    return result.retrieved_document_ids[:k]


def _average(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 6) if values else None


def _mean_reciprocal_rank(results: Sequence[QueryOutcome], k: int) -> float | None:
    answerable = [result for result in results if result.answerable]
    if not answerable:
        return None
    reciprocal_ranks = []
    for result in answerable:
        relevant = set(result.expected_document_ids)
        rank = next(
            (index for index, document_id in enumerate(_documents_at_chunk_cutoff(result, k), 1)
             if document_id in relevant),
            None,
        )
        reciprocal_ranks.append(1 / rank if rank is not None else 0.0)
    return _average(reciprocal_ranks)


def summarize_group(results: Sequence[QueryOutcome], *, ks: tuple[int, ...] = (1, 3, 5)) -> dict:
    answerable = [result for result in results if result.answerable]
    unanswerable = [result for result in results if not result.answerable]
    recall_at_k: dict[str, float | None] = {}
    hit_at_k: dict[str, float | None] = {}
    source_precision_at_k: dict[str, float | None] = {}
    chunk_recall_at_k: dict[str, float | None] = {}

    for k in ks:
        document_recalls: list[float] = []
        hits: list[float] = []
        relevant_sources = 0
        returned_sources = 0
        labeled_chunk_recalls: list[float] = []
        for result in answerable:
            expected_documents = set(result.expected_document_ids)
            returned_documents = _documents_at_chunk_cutoff(result, k)
            found_documents = expected_documents.intersection(returned_documents)
            document_recalls.append(len(found_documents) / len(expected_documents))
            hits.append(float(bool(found_documents)))
            relevant_sources += len(found_documents)
            returned_sources += len(returned_documents)

            if result.expected_chunk_ids:
                found_chunks = set(result.expected_chunk_ids).intersection(result.retrieved_chunk_ids[:k])
                labeled_chunk_recalls.append(len(found_chunks) / len(result.expected_chunk_ids))

        key = str(k)
        recall_at_k[key] = _average(document_recalls)
        hit_at_k[key] = _average(hits)
        source_precision_at_k[key] = (
            round(relevant_sources / returned_sources, 6) if returned_sources else None
        )
        chunk_recall_at_k[key] = _average(labeled_chunk_recalls)

    candidate_returns = [
        float(bool(result.retrieved_chunk_ids or result.retrieved_document_ids))
        for result in unanswerable
    ]
    no_answer_scores = [result.top_score for result in unanswerable if result.top_score is not None]
    embedding_times = [result.embedding_latency_ms for result in results]
    retrieval_times = [result.retrieval_latency_ms for result in results]

    return {
        "query_count": len(results),
        "answerable_query_count": len(answerable),
        "unanswerable_query_count": len(unanswerable),
        "recall_at_k": recall_at_k,
        "hit_at_k": hit_at_k,
        "mrr_at_k": {str(k): _mean_reciprocal_rank(results, k) for k in ks},
        "source_precision_at_k": source_precision_at_k,
        "chunk_recall_at_k": chunk_recall_at_k,
        "unanswerable_candidate_return_rate": _average(candidate_returns),
        "unanswerable_mean_top_score": _average(no_answer_scores),
        "median_embedding_latency_ms": round(median(embedding_times), 3) if embedding_times else None,
        "median_retrieval_latency_ms": round(median(retrieval_times), 3) if retrieval_times else None,
    }


def aggregate_metrics(results: Sequence[QueryOutcome]) -> dict:
    """Aggregate each case once globally; subgroup categories intentionally overlap."""
    languages = ("tr", "en", "mixed")
    categories = (
        "single_document_fact",
        "multi_document",
        "long_document",
        "semantic_distractors",
        "unanswerable",
    )
    return {
        "global": summarize_group(results),
        "by_language": {
            language: summarize_group([item for item in results if item.language == language])
            for language in languages
        },
        "by_category": {
            category: summarize_group([item for item in results if category in item.categories])
            for category in categories
        },
    }
