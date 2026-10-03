"""Authorized RAG evaluation runner and dataset loader."""

from __future__ import annotations

import json
import math
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from statistics import median
from time import perf_counter

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.authorization import resolve_knowledge_base_scope
from app.core.config import get_settings
from app.models.schemas import Source
from app.services.evaluation.adaptive import (
    AdaptivePolicy,
    adaptive_context_k,
    retrieval_score_features,
)
from app.services.evaluation.metrics import (
    answer_fact_groundedness,
    fact_coverage,
    normalize_text,
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
    dataset_fingerprint,
)
from app.services.evaluation.reranker import RerankerEvaluationError, RerankerProvider
from app.services.rag.pipeline import build_rag_prompt, retrieve_rag_context

Retriever = Callable[[EvaluationCase], Awaitable[RetrievalResult]]
Generator = Callable[[EvaluationCase, RetrievalResult], Awaitable[str]]


class AuthorizationExpectationError(RuntimeError):
    """A labelled authorization-denial probe was unexpectedly allowed."""


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
            retrieval_scores=[source.score for source in context.sources[: case.top_k]],
        )


class AdaptiveContextRetriever:
    """Evaluation-only wrapper that selects a context prefix from a K=3 result."""

    def __init__(
        self,
        retrieve: Retriever,
        *,
        policy: AdaptivePolicy,
        threshold: float,
        second_threshold: float | None = None,
    ):
        self.retrieve = retrieve
        self.policy = policy
        self.threshold = threshold
        self.second_threshold = second_threshold

    async def __call__(self, case: EvaluationCase) -> RetrievalResult:
        result = await self.retrieve(case)
        evidence = result.evidence[: case.top_k]
        scores = result.retrieval_scores or [item.score for item in evidence]
        selected_count = adaptive_context_k(
            scores,
            policy=self.policy,
            threshold=self.threshold,
            second_threshold=self.second_threshold,
        )
        selected = evidence[:selected_count]
        return RetrievalResult(
            evidence=selected,
            prompt=build_rag_prompt(case.question, [item.text or "" for item in selected]),
            embedding_latency_ms=result.embedding_latency_ms,
            retrieval_latency_ms=result.retrieval_latency_ms,
            retrieval_scores=scores,
        )


class RerankedContextRetriever:
    """Evaluation-only candidate-pool reranking, then a fixed final context prefix."""

    def __init__(
        self,
        retrieve: Retriever,
        provider: RerankerProvider,
        *,
        candidate_pool_size: int,
        top_n: int = 3,
    ):
        if top_n <= 0:
            raise ValueError("top_n must be positive")
        if candidate_pool_size < top_n or candidate_pool_size > 50:
            raise ValueError("candidate_pool_size must be between top_n and 50")
        self.retrieve = retrieve
        self.provider = provider
        self.candidate_pool_size = candidate_pool_size
        self.top_n = top_n

    async def __call__(self, case: EvaluationCase) -> RetrievalResult:
        candidate_case = case.model_copy(update={"top_k": self.candidate_pool_size})
        vector_result = await self.retrieve(candidate_case)
        candidates = [
            item.model_copy(update={"vector_rank": item.vector_rank or rank})
            for rank, item in enumerate(vector_result.evidence[: self.candidate_pool_size], start=1)
        ]
        expected_candidate_ranks = _expected_document_ranks(case, candidates)
        started = perf_counter()
        reranked = await self.provider.rerank(case.question, candidates, self.top_n)
        reranker_latency_ms = (perf_counter() - started) * 1000

        expected_count = min(self.top_n, len(candidates))
        if len(reranked) != expected_count:
            raise RerankerEvaluationError(
                f"reranker returned {len(reranked)} candidates; expected {expected_count}"
            )
        candidate_by_identity = {_evidence_identity(item): item for item in candidates}
        if len(candidate_by_identity) != len(candidates):
            raise RerankerEvaluationError("vector candidate pool contains duplicate identities")

        final_evidence: list[RetrievedEvidence] = []
        seen: set[tuple[object, ...]] = set()
        for ranked in reranked:
            if not math.isfinite(ranked.score):
                raise RerankerEvaluationError("reranker returned a non-finite score")
            identity = _evidence_identity(ranked.evidence)
            original = candidate_by_identity.get(identity)
            if original is None or identity in seen:
                raise RerankerEvaluationError("reranker changed or duplicated candidate identity")
            seen.add(identity)
            final_evidence.append(
                original.model_copy(update={"reranker_score": ranked.score})
            )

        return RetrievalResult(
            evidence=final_evidence,
            prompt=build_rag_prompt(
                case.question,
                [item.text or "" for item in final_evidence],
            ),
            embedding_latency_ms=vector_result.embedding_latency_ms,
            retrieval_latency_ms=vector_result.retrieval_latency_ms,
            retrieval_scores=vector_result.retrieval_scores
            or [item.score for item in candidates],
            reranker_latency_ms=reranker_latency_ms,
            candidate_pool_size=len(candidates),
            candidate_expected_document_ranks=expected_candidate_ranks,
        )


def _to_evidence(source: Source) -> RetrievedEvidence:
    return RetrievedEvidence(
        document=source.document,
        score=source.score,
        document_id=source.document_id,
        chunk_index=source.chunk_index,
        text=source.text,
    )


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
        top_k_override: int | None = None,
    ) -> EvaluationResult:
        if mode not in {"fixture", "local"}:
            raise ValueError("mode must be fixture or local")
        if top_k_override is not None and not 1 <= top_k_override <= 50:
            raise ValueError("top_k_override must be between 1 and 50")
        # Do not mutate the validated dataset: its canonical fingerprint remains
        # the identity of the authored evaluation corpus, not this runtime sweep.
        runtime_cases = [
            case.model_copy(update={"top_k": top_k_override}) if top_k_override is not None else case
            for case in dataset.cases
        ]
        cases = [await self._run_case(case) for case in runtime_cases]
        configured = configured_models()
        configured.update(models or {})
        metadata = run_metadata(configured)
        effective_values = {case.top_k for case in runtime_cases}
        return EvaluationResult(
            dataset_version=dataset.version,
            dataset_name=dataset.name,
            dataset_fingerprint=dataset_fingerprint(dataset),
            mode=mode,
            models=configured,
            evaluation_mode=mode,
            effective_top_k=next(iter(effective_values)) if len(effective_values) == 1 else None,
            top_k_override=top_k_override,
            summary=_summarize(cases),
            cases=cases,
            **metadata,
        )

    async def _run_case(self, case: EvaluationCase) -> EvaluationCaseResult:
        started = perf_counter()
        try:
            retrieval = await self.retrieve(case)
        except HTTPException as exc:
            if case.authorization_expectation == "deny" and exc.status_code in {401, 403, 404}:
                return _authorization_denied_result(case, (perf_counter() - started) * 1000)
            raise
        if case.authorization_expectation == "deny":
            raise AuthorizationExpectationError(
                f"case {case.id} expected authorization denial but retrieval was allowed"
            )
        answer: str | None = None
        generation_ms: float | None = None
        if self.generate is not None and case.expect_answer:
            generation_started = perf_counter()
            answer = await self.generate(case, retrieval)
            generation_ms = (perf_counter() - generation_started) * 1000
        total_ms = (perf_counter() - started) * 1000

        evidence = retrieval.evidence[: case.top_k]
        returned_documents = [item.document for item in evidence]
        source_matches = _source_matches(case, evidence)
        scores = retrieval.retrieval_scores
        if scores is None:
            scores = [item.score for item in evidence]
        score_features = retrieval_score_features(scores)
        has_expected_source_identity = bool(case.expected_document_ids or case.expected_documents)
        source_hit = any(source_matches) if has_expected_source_identity else None
        first_match_index = next((index for index, matched in enumerate(source_matches, start=1) if matched), None)
        unexpected = [
            document
            for document, matched in zip(returned_documents, source_matches, strict=True)
            if has_expected_source_identity and not matched
        ]
        source_texts = [item.text for item in evidence]
        expected_document_candidate_ranks = (
            retrieval.candidate_expected_document_ranks
            or _expected_document_ranks(case, evidence)
        )
        confusable_ids = set(case.confusable_document_ids)
        no_answer_confusables = (
            sum(item.document_id in confusable_ids for item in evidence)
            if case.case_type == "no_answer"
            else 0
        )
        return EvaluationCaseResult(
            case_id=case.id,
            category=case.category,
            case_type=case.case_type,
            language=case.language,
            expect_answer=case.expect_answer,
            knowledge_base_ids=case.knowledge_base_ids,
            effective_top_k=case.top_k,
            expected_documents=case.expected_documents,
            expected_document_ids=case.expected_document_ids,
            returned_documents=returned_documents,
            returned_document_ids=[item.document_id for item in evidence],
            returned_chunk_indexes=[item.chunk_index for item in evidence],
            source_hit=source_hit,
            reciprocal_rank=(1.0 / first_match_index) if first_match_index is not None else (0.0 if has_expected_source_identity else None),
            unexpected_sources=unexpected,
            no_source_returned=not returned_documents,
            retrieved_source_count=len(evidence),
            retrieved_chunk_count=len(evidence),
            expected_fact_count=len(case.expected_facts),
            facts_supported_by_sources=supported_fact_count(case.expected_facts, source_texts),
            fact_coverage=(fact_coverage(case.expected_facts, source_texts) if case.expect_answer else None),
            answer_fact_groundedness=(
                answer_fact_groundedness(case.expected_facts, source_texts, answer)
                if case.expect_answer
                else None
            ),
            generated_answer_char_count=len(answer) if answer is not None else None,
            **score_features.__dict__,
            expected_source_rank=next(
                (rank for rank, matched in enumerate(source_matches, start=1) if matched), None
            ),
            relevant_source_by_rank=source_matches,
            fact_coverage_by_rank=[
                fact_coverage(case.expected_facts, source_texts[:rank])
                for rank in range(1, len(source_texts) + 1)
            ] if case.expect_answer else [],
            returned_vector_ranks=[
                item.vector_rank or rank
                for rank, item in enumerate(evidence, start=1)
            ],
            expected_document_candidate_ranks=expected_document_candidate_ranks,
            expected_source_vector_rank=min(
                (rank for rank in expected_document_candidate_ranks if rank is not None),
                default=None,
            ),
            no_answer_confusable_source_count=no_answer_confusables,
            candidate_pool_size=retrieval.candidate_pool_size,
            latencies=CaseLatencies(
                embedding_ms=retrieval.embedding_latency_ms,
                retrieval_ms=retrieval.retrieval_latency_ms,
                reranker_ms=retrieval.reranker_latency_ms,
                generation_ms=generation_ms,
                total_ms=total_ms,
            ),
        )


def configured_models() -> dict[str, str | None]:
    settings = get_settings()
    return {"embedding_model": settings.embedding_model, "generation_model": settings.ollama_model}


def run_metadata(models: dict[str, str | None]) -> dict[str, str | int | None]:
    """Return reproducibility metadata without evaluating or persisting user content."""
    settings = get_settings()
    return {
        "embedding_model": models.get("embedding_model"),
        "generation_provider": "ollama" if models.get("generation_model") else None,
        "generation_model": models.get("generation_model"),
        "rag_top_k_default": settings.rag_top_k,
        "application_version": _git_commit_sha(),
    }


def _git_commit_sha() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    commit = completed.stdout.strip()
    return commit or None


def _source_matches(case: EvaluationCase, evidence: list[RetrievedEvidence]) -> list[bool]:
    """Prefer stable document IDs; filename matching is legacy fallback only."""
    if case.expected_document_ids:
        expected_ids = set(case.expected_document_ids)
        return [item.document_id in expected_ids for item in evidence]
    expected_names = {normalize_text(document) for document in case.expected_documents}
    return [normalize_text(item.document) in expected_names for item in evidence] if expected_names else [False] * len(evidence)


def _expected_document_ranks(
    case: EvaluationCase,
    evidence: list[RetrievedEvidence],
) -> list[int | None]:
    """Return ranks aligned to each expected stable ID, falling back to filenames."""
    if case.expected_document_ids:
        return [
            next(
                (rank for rank, item in enumerate(evidence, start=1) if item.document_id == identifier),
                None,
            )
            for identifier in case.expected_document_ids
        ]
    if case.expected_documents:
        return [
            next(
                (
                    rank
                    for rank, item in enumerate(evidence, start=1)
                    if normalize_text(item.document) == normalize_text(document)
                ),
                None,
            )
            for document in case.expected_documents
        ]
    return []


def _evidence_identity(item: RetrievedEvidence) -> tuple[object, ...]:
    if item.document_id is not None:
        return ("id", item.document_id, item.chunk_index)
    return ("name", normalize_text(item.document), item.chunk_index, item.score)


def _authorization_denied_result(case: EvaluationCase, total_ms: float) -> EvaluationCaseResult:
    return EvaluationCaseResult(
        case_id=case.id,
        category=case.category,
        case_type=case.case_type,
        language=case.language,
        expect_answer=False,
        scope_denied=True,
        knowledge_base_ids=case.knowledge_base_ids,
        effective_top_k=case.top_k,
        expected_documents=[],
        expected_document_ids=[],
        returned_documents=[],
        returned_document_ids=[],
        returned_chunk_indexes=[],
        source_hit=None,
        reciprocal_rank=None,
        unexpected_sources=[],
        no_source_returned=True,
        retrieved_source_count=0,
        retrieved_chunk_count=0,
        expected_fact_count=0,
        facts_supported_by_sources=0,
        fact_coverage=None,
        answer_fact_groundedness=None,
        generated_answer_char_count=None,
        expected_source_rank=None,
        no_answer_confusable_source_count=0,
        latencies=CaseLatencies(total_ms=total_ms),
    )


def _mean(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(sum(numeric) / len(numeric), 6) if numeric else None


def _median(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    return round(median(numeric), 3) if numeric else None


def _summarize(cases: list[EvaluationCaseResult]) -> EvaluationSummary:
    source_evaluated = [case.source_hit for case in cases if case.source_hit is not None]
    source_identity_cases = [case for case in cases if case.source_hit is not None]
    returned_source_count = sum(len(case.returned_documents) for case in source_identity_cases)
    correct_source_count = sum(
        sum(
            item_id in set(case.expected_document_ids)
            if case.expected_document_ids
            else normalize_text(document) in {normalize_text(name) for name in case.expected_documents}
            for item_id, document in zip(case.returned_document_ids, case.returned_documents, strict=True)
        )
        for case in source_identity_cases
    )
    return EvaluationSummary(
        case_count=len(cases),
        answerable_case_count=sum(case.expect_answer for case in cases),
        no_answer_case_count=sum(case.case_type == "no_answer" for case in cases),
        access_probe_case_count=sum(
            case.case_type == "authorization_negative" for case in cases
        ),
        scope_denial_count=sum(case.scope_denied for case in cases),
        normal_case_count=sum(case.case_type == "normal" for case in cases),
        hard_negative_case_count=sum(case.case_type == "hard_negative" for case in cases),
        multi_fact_case_count=sum(case.expect_answer and case.expected_fact_count > 1 for case in cases),
        no_answer_confusable_case_count=sum(
            case.case_type == "no_answer" and case.no_answer_confusable_source_count > 0
            for case in cases
        ),
        no_answer_confusable_source_count=sum(
            case.no_answer_confusable_source_count for case in cases
        ),
        hit_at_k=_mean([1.0 if hit else 0.0 for hit in source_evaluated]),
        mean_reciprocal_rank=_mean([case.reciprocal_rank for case in cases]),
        source_accuracy=(
            round(correct_source_count / returned_source_count, 6) if returned_source_count else None
        ),
        source_hit_count=sum(hit is True for hit in source_evaluated),
        unexpected_source_count=sum(len(case.unexpected_sources) for case in cases),
        no_source_count=sum(case.no_source_returned and not case.scope_denied for case in cases),
        fact_coverage=_mean([case.fact_coverage for case in cases]),
        answer_fact_groundedness=_mean([case.answer_fact_groundedness for case in cases]),
        median_embedding_ms=_median([case.latencies.embedding_ms for case in cases]),
        median_retrieval_ms=_median([case.latencies.retrieval_ms for case in cases]),
        median_generation_ms=_median([case.latencies.generation_ms for case in cases]),
        median_reranker_ms=_median([case.latencies.reranker_ms for case in cases]),
        median_total_ms=_median(
            [case.latencies.total_ms for case in cases if not case.scope_denied]
        ),
        mean_retrieved_source_count=_mean(
            [float(case.retrieved_source_count) for case in cases if not case.scope_denied]
        ),
        median_retrieved_source_count=_median(
            [float(case.retrieved_source_count) for case in cases if not case.scope_denied]
        ),
        median_retrieved_chunk_count=_median(
            [float(case.retrieved_chunk_count) for case in cases if not case.scope_denied]
        ),
        median_generated_answer_char_count=_median(
            [float(case.generated_answer_char_count) if case.generated_answer_char_count is not None else None for case in cases]
        ),
    )
