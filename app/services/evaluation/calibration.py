"""Deterministic group holdouts and calibration-only adaptive threshold selection."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Iterable

from app.services.evaluation.adaptive import AdaptivePolicy, summarize_adaptive_policy
from app.services.evaluation.models import EvaluationDataset, EvaluationResult


def split_calibration_holdout(
    dataset: EvaluationDataset,
    *,
    holdout_fraction: float = 0.25,
    seed: str = "retrieval-robustness-v1",
) -> tuple[EvaluationDataset, EvaluationDataset]:
    """Split by scenario group with a stable hash, preventing near-duplicate leakage."""
    if not math.isfinite(holdout_fraction) or not 0 < holdout_fraction < 1:
        raise ValueError("holdout_fraction must be between 0 and 1")
    groups: dict[str, list] = {}
    for case in dataset.cases:
        group_id = f"scenario:{case.scenario_id}" if case.scenario_id else f"case:{case.id}"
        groups.setdefault(group_id, []).append(case)
    if len(groups) < 2:
        raise ValueError("at least two independent case/scenario groups are required")

    ordered_groups = sorted(
        groups,
        key=lambda group_id: hashlib.sha256(f"{seed}:{group_id}".encode("utf-8")).hexdigest(),
    )
    holdout_count = max(1, min(len(ordered_groups) - 1, round(len(ordered_groups) * holdout_fraction)))
    holdout_groups = set(ordered_groups[:holdout_count])
    calibration_cases = []
    holdout_cases = []
    for case in dataset.cases:
        group_id = f"scenario:{case.scenario_id}" if case.scenario_id else f"case:{case.id}"
        (holdout_cases if group_id in holdout_groups else calibration_cases).append(case)

    return (
        dataset.model_copy(update={"name": f"{dataset.name}-calibration", "cases": calibration_cases}),
        dataset.model_copy(update={"name": f"{dataset.name}-holdout", "cases": holdout_cases}),
    )


def select_adaptive_candidate(
    calibration_result: EvaluationResult,
    *,
    policy: AdaptivePolicy,
) -> dict[str, object]:
    """Select the lowest-context threshold preserving K=3 metrics on calibration only."""
    cases = [
        case.model_dump(mode="python")
        for case in calibration_result.cases
        if case.expect_answer and case.source_hit is not None
    ]
    if not cases:
        raise ValueError("calibration split contains no answerable source-labeled cases")

    baseline = summarize_adaptive_policy(cases, policy="gap", threshold=10.0)
    gap23_values = _candidate_values(cases, "score_gap_2_3")
    ratio32_values = _candidate_values(cases, "score_ratio_3_2")
    gap12_values = _candidate_values(cases, "score_gap_1_2")
    if policy == "gap":
        candidates = [(threshold, None) for threshold in gap23_values]
    elif policy == "ratio":
        candidates = [(threshold, None) for threshold in ratio32_values]
    elif policy == "three_tier":
        candidates = [(gap23, gap12) for gap23 in gap23_values for gap12 in gap12_values]
    else:
        raise ValueError(f"unsupported adaptive policy: {policy}")

    passing: list[tuple[tuple[float, float, float, float, float], float, float | None, dict[str, object]]] = []
    for threshold, second_threshold in candidates:
        metrics = summarize_adaptive_policy(
            cases,
            policy=policy,
            threshold=threshold,
            second_threshold=second_threshold,
        )
        if not _preserves_quality(baseline, metrics):
            continue
        mean_context = metrics.get("mean_source_count")
        if mean_context is None or mean_context >= 3.0:
            continue
        tie_break = (
            float(mean_context),
            -_metric(metrics, "source_accuracy"),
            -_metric(metrics, "mean_reciprocal_rank"),
            threshold,
            second_threshold if second_threshold is not None else -math.inf,
        )
        passing.append((tie_break, threshold, second_threshold, metrics))

    if not passing:
        return {
            "policy": policy,
            "selected": False,
            "threshold": None,
            "second_threshold": None,
            "calibration_case_count": len(cases),
            "baseline_metrics": baseline,
            "metrics": None,
        }

    _, threshold, second_threshold, metrics = min(passing, key=lambda item: item[0])
    return {
        "policy": policy,
        "selected": True,
        "threshold": threshold,
        "second_threshold": second_threshold,
        "calibration_case_count": len(cases),
        "baseline_metrics": baseline,
        "metrics": metrics,
        "passing_threshold_count": len(passing),
    }


def evaluate_adaptive_candidate(
    holdout_result: EvaluationResult,
    selection: dict[str, object],
) -> dict[str, object] | None:
    if not selection.get("selected"):
        return None
    cases = [
        case.model_dump(mode="python")
        for case in holdout_result.cases
        if case.expect_answer and case.source_hit is not None
    ]
    if not cases:
        raise ValueError("holdout split contains no answerable source-labeled cases")
    return summarize_adaptive_policy(
        cases,
        policy=selection["policy"],
        threshold=float(selection["threshold"]),
        second_threshold=(
            float(selection["second_threshold"])
            if selection.get("second_threshold") is not None
            else None
        ),
    )


def _candidate_values(cases: list[dict[str, object]], field: str) -> list[float]:
    values = sorted(
        {
            float(case[field])
            for case in cases
            if case.get(field) is not None and math.isfinite(float(case[field]))
        }
    )
    if not values:
        return [0.0]
    return values


def _preserves_quality(baseline: dict[str, object], candidate: dict[str, object]) -> bool:
    for metric in ("hit_at_k", "mean_reciprocal_rank", "source_accuracy", "fact_coverage"):
        expected = baseline.get(metric)
        actual = candidate.get(metric)
        if expected is not None and (actual is None or float(actual) + 1e-9 < float(expected)):
            return False
    return True


def _metric(metrics: dict[str, object], key: str) -> float:
    value = metrics.get(key)
    return float(value) if value is not None else 0.0
