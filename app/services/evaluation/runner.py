"""Authorized RAG evaluation runner and dataset loader."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from pathlib import Path
from statistics import median
from time import perf_counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import resolve_knowledge_base_scope
from app.core.config import get_settings
from app.models.schemas import Source
from app.services.evaluation.metrics import (
    answer_fact_groundedness,
    document_matches,
    fact_coverage,
    hit_at_k,
    normalize_text,
    reciprocal_rank,
    supported_fact_count,
)
from app.services.evaluation.models import (
    CaseLatencies,
    EvaluationCase,
    EvaluationCaseResult,
    EvaluationDataset,
    EvaluationResult,
    EvaluationSummary,
    RetrievalResult,
    RetrievedEvidence,
)
from app.services.rag.pipeline import retrieve_rag_context

Retriever = Callable[[EvaluationCase], Awaitable[RetrievalResult]]
Generator = Callable[[EvaluationCase, RetrievalResult], Awaitable[str]]


def load_dataset(path: str | Path) -> EvaluationDataset:
    """Load and validate the public versioned JSON dataset format."""
    try:
        content = Path(path).read_text(encoding="utf-8")
        return EvaluationDataset.model_validate_json(content)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Invalid evaluation dataset: {exc}") from exc


class AuthorizedRagRetriever:
    """Retrieve only through the exact KB authorization boundary used by /rag/query."""

    def __init__(self, db: AsyncSession, user: dict):
        self.db = db
        self.user = user

    async def __call__(self, case: EvaluationCase) -> RetrievalResult:
        knowledge_base_ids, kb_scope = await resolve_knowledge_base_scope(
            self.db, self.user, case.knowledge_base_ids
        )
        context = await retrieve_rag_context(
            case.question,
            user_id=int(self.user["sub"]),
            organization_id=kb_scope[1].organization_id if kb_scope else None,
            workspace_id=kb_scope[1].id if kb_scope else None,
            knowledge_base_ids=knowledge_base_ids,
            limit=case.top_k,
        )
        return RetrievalResult(
            evidence=[_to_evidence(source) for source in context.sources[: case.top_k]],
            prompt=context.prompt,
            embedding_latency_ms=context.embedding_latency_ms,
            retrieval_latency_ms=context.retrieval_latency_ms,
        )


def _to_evidence(source: Source) -> RetrievedEvidence:
    return RetrievedEvidence(document=source.document, score=source.score, text=source.text)


class EvaluationRunner:
    def __init__(self, retrieve: Retriever, generate: Generator | None = None):
        self.retrieve = retrieve
        self.generate = generate

    async def run(
        self,
        dataset: EvaluationDataset,
        *,
        mode: str,
        models: dict[str, str | None] | None = None,
    ) -> EvaluationResult:
        if mode not in {"fixture", "local"}:
            raise ValueError("mode must be fixture or local")
        cases = [await self._run_case(case) for case in dataset.cases]
        return EvaluationResult(
            dataset_version=dataset.version,
            dataset_name=dataset.name,
            mode=mode,
            models=models or configured_models(),
            summary=_summarize(cases),
            cases=cases,
        )

    async def _run_case(self, case: EvaluationCase) -> EvaluationCaseResult:
        started = perf_counter()
        retrieval = await self.retrieve(case)
        answer: str | None = None
        generation_ms: float | None = None
        if self.generate is not None:
            generation_started = perf_counter()
            answer = await self.generate(case, retrieval)
            generation_ms = (perf_counter() - generation_started) * 1000
        total_ms = (perf_counter() - started) * 1000

        evidence = retrieval.evidence[: case.top_k]
        returned_documents = [item.document for item in evidence]
        expected_documents = case.expected_documents
        source_hit = hit_at_k(expected_documents, returned_documents)
        expected_normalized = {normalize_text(document) for document in expected_documents}
        unexpected = [
            document for document in returned_documents if normalize_text(document) not in expected_normalized
        ]
        source_texts = [item.text for item in evidence]
        return EvaluationCaseResult(
            case_id=case.id,
            category=case.category,
            knowledge_base_ids=case.knowledge_base_ids,
            expected_documents=expected_documents,
            returned_documents=returned_documents,
            source_hit=source_hit,
            reciprocal_rank=reciprocal_rank(expected_documents, returned_documents),
            unexpected_sources=unexpected,
            no_source_returned=not returned_documents,
            expected_fact_count=len(case.expected_facts),
            facts_supported_by_sources=supported_fact_count(case.expected_facts, source_texts),
            fact_coverage=fact_coverage(case.expected_facts, source_texts),
            answer_fact_groundedness=answer_fact_groundedness(case.expected_facts, source_texts, answer),
            latencies=CaseLatencies(
                embedding_ms=retrieval.embedding_latency_ms,
                retrieval_ms=retrieval.retrieval_latency_ms,
                generation_ms=generation_ms,
                total_ms=total_ms,
            ),
        )


def configured_models() -> dict[str, str | None]:
    settings = get_settings()
    return {"embedding_model": settings.embedding_model, "generation_model": settings.ollama_model}


def _mean(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(sum(numeric) / len(numeric), 6) if numeric else None


def _median(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(median(numeric), 3) if numeric else None


def _summarize(cases: list[EvaluationCaseResult]) -> EvaluationSummary:
    source_evaluated = [case.source_hit for case in cases if case.source_hit is not None]
    returned_source_count = sum(len(case.returned_documents) for case in cases)
    correct_source_count = sum(
        sum(document_matches(case.expected_documents, case.returned_documents)) for case in cases
    )
    return EvaluationSummary(
        case_count=len(cases),
        hit_at_k=_mean([1.0 if hit else 0.0 for hit in source_evaluated]),
        mean_reciprocal_rank=_mean([case.reciprocal_rank for case in cases]),
        source_accuracy=(
            round(correct_source_count / returned_source_count, 6) if returned_source_count else None
        ),
        source_hit_count=sum(hit is True for hit in source_evaluated),
        unexpected_source_count=sum(len(case.unexpected_sources) for case in cases),
        no_source_count=sum(case.no_source_returned for case in cases),
        fact_coverage=_mean([case.fact_coverage for case in cases]),
        answer_fact_groundedness=_mean([case.answer_fact_groundedness for case in cases]),
        median_embedding_ms=_median([case.latencies.embedding_ms for case in cases]),
        median_retrieval_ms=_median([case.latencies.retrieval_ms for case in cases]),
        median_generation_ms=_median([case.latencies.generation_ms for case in cases]),
        median_total_ms=_median([case.latencies.total_ms for case in cases]),
    )
