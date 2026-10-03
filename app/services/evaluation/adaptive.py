"""Deterministic, evaluation-only helpers for adaptive context experiments."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import isfinite
from statistics import mean, median
from typing import Literal


AdaptivePolicy = Literal["gap", "ratio", "three_tier"]


@dataclass(frozen=True)
class RetrievalScoreFeatures:
    top1_score: float | None
    top2_score: float | None
    top3_score: float | None
    score_gap_1_2: float | None
    score_gap_2_3: float | None
    score_ratio_2_1: float | None
    score_ratio_3_1: float | None
    score_ratio_3_2: float | None


def retrieval_score_features(scores: list[float]) -> RetrievalScoreFeatures:
    """Return numeric top-three score features; ratios need positive denominators."""
    top = [float(score) for score in scores[:3]]
    top1 = top[0] if len(top) > 0 else None
    top2 = top[1] if len(top) > 1 else None
    top3 = top[2] if len(top) > 2 else None
    return RetrievalScoreFeatures(
        top1_score=top1,
        top2_score=top2,
        top3_score=top3,
        score_gap_1_2=top1 - top2 if top1 is not None and top2 is not None else None,
        score_gap_2_3=top2 - top3 if top2 is not None and top3 is not None else None,
        score_ratio_2_1=_positive_ratio(top2, top1),
        score_ratio_3_1=_positive_ratio(top3, top1),
        score_ratio_3_2=_positive_ratio(top3, top2),
    )


def adaptive_context_k(
    scores: list[float],
    *,
    policy: AdaptivePolicy,
    threshold: float,
    second_threshold: float | None = None,
) -> int:
    """Select a context count using only the ordered scores from one query."""
    if not isfinite(threshold) or (second_threshold is not None and not isfinite(second_threshold)):
        raise ValueError("adaptive thresholds must be finite")
    available = min(len(scores), 3)
    if available < 2:
        return available

    features = retrieval_score_features(scores)
    if policy == "gap":
        if features.score_gap_2_3 is not None and features.score_gap_2_3 <= threshold:
            return 3
        return 2
    if policy == "ratio":
        if features.score_ratio_3_2 is not None and features.score_ratio_3_2 >= threshold:
            return 3
        return 2
    if policy == "three_tier":
        if second_threshold is None:
            raise ValueError("three_tier requires second_threshold")
        if features.score_gap_1_2 is not None and features.score_gap_1_2 > second_threshold:
            return 1
        if features.score_gap_2_3 is not None and features.score_gap_2_3 <= threshold:
            return 3
        return 2
    raise ValueError(f"unsupported adaptive policy: {policy}")


def summarize_adaptive_policy(
    cases: Sequence[Mapping[str, object]],
    *,
    policy: AdaptivePolicy,
    threshold: float,
    second_threshold: float | None = None,
) -> dict[str, object]:
    """Evaluate a policy from safe per-case metadata emitted by a K=3 run."""
    selected_counts: list[int] = []
    hits: list[float] = []
    reciprocal_ranks: list[float] = []
    fact_coverages: list[float] = []
    correct_sources = 0
    returned_sources = 0
    count_distribution = {0: 0, 1: 0, 2: 0, 3: 0}

    for case in cases:
        scores = [
            float(case[field])
            for field in ("top1_score", "top2_score", "top3_score")
            if case.get(field) is not None
        ]
        selected = adaptive_context_k(
            scores,
            policy=policy,
            threshold=threshold,
            second_threshold=second_threshold,
        )
        selected_counts.append(selected)
        count_distribution[selected] += 1

        if case.get("source_hit") is not None:
            expected_rank = case.get("expected_source_rank")
            is_hit = expected_rank is not None and int(expected_rank) <= selected
            hits.append(float(is_hit))
            reciprocal_ranks.append(1.0 / int(expected_rank) if is_hit else 0.0)
            rank_matches = case.get("relevant_source_by_rank") or []
            correct_sources += sum(bool(value) for value in rank_matches[:selected])
            returned_sources += min(selected, len(rank_matches))

        coverage_by_rank = case.get("fact_coverage_by_rank") or []
        if selected and len(coverage_by_rank) >= selected:
            coverage = coverage_by_rank[selected - 1]
            if coverage is not None:
                fact_coverages.append(float(coverage))

    return {
        "case_count": len(cases),
        "hit_at_k": _mean(hits),
        "mean_reciprocal_rank": _mean(reciprocal_ranks),
        "source_accuracy": round(correct_sources / returned_sources, 6) if returned_sources else None,
        "fact_coverage": _mean(fact_coverages),
        "mean_source_count": round(mean(selected_counts), 6) if selected_counts else None,
        "median_source_count": round(median(selected_counts), 3) if selected_counts else None,
        "source_count_distribution": count_distribution,
    }


def _positive_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _mean(values: list[float]) -> float | None:
    return round(mean(values), 6) if values else None
