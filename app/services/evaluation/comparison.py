"""Objective comparison of two versioned RAG evaluation runs."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.evaluation.models import EvaluationResult


METRICS = (
    "hit_at_k",
    "mean_reciprocal_rank",
    "source_accuracy",
    "fact_coverage",
    "answer_fact_groundedness",
    "median_embedding_ms",
    "median_retrieval_ms",
    "median_generation_ms",
    "median_total_ms",
)


class EvaluationComparison(BaseModel):
    baseline_dataset: str
    candidate_dataset: str
    deltas: dict[str, float | None]
    warnings: list[str] = Field(default_factory=list)
    missing_case_ids: dict[str, list[str]] = Field(default_factory=dict)


def compare_evaluations(baseline: EvaluationResult, candidate: EvaluationResult) -> EvaluationComparison:
    warnings: list[str] = []
    if baseline.models.get("embedding_model") != candidate.models.get("embedding_model"):
        warnings.append("Embedding model changed; reindex knowledge bases before treating retrieval deltas as comparable.")
    if baseline.dataset_version != candidate.dataset_version:
        warnings.append("Dataset versions differ; metric deltas may not be directly comparable.")
    baseline_ids = {case.case_id for case in baseline.cases}
    candidate_ids = {case.case_id for case in candidate.cases}
    return EvaluationComparison(
        baseline_dataset=baseline.dataset_name,
        candidate_dataset=candidate.dataset_name,
        deltas={
            metric: _delta(getattr(baseline.summary, metric), getattr(candidate.summary, metric))
            for metric in METRICS
        },
        warnings=warnings,
        missing_case_ids={
            "only_in_baseline": sorted(baseline_ids - candidate_ids),
            "only_in_candidate": sorted(candidate_ids - baseline_ids),
        },
    )


def _delta(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None:
        return None
    return round(candidate - baseline, 6)
