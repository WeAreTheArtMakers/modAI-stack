"""Aggregate-only helpers for cross-language retrieval diagnostics."""

from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping, Sequence


RANK_BUCKETS = ("1", "2", "3", "4-5", "6-10", "11-20", ">20/miss")


def rank_bucket(rank: int | None) -> str:
    if rank is None or rank > 20:
        return ">20/miss"
    if rank <= 0:
        raise ValueError("rank must be positive or None")
    if rank <= 3:
        return str(rank)
    if rank <= 5:
        return "4-5"
    if rank <= 10:
        return "6-10"
    return "11-20"


def _percentile(values: Sequence[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, math.ceil(fraction * len(ordered)) - 1)
    return ordered[index]


def score_distribution(values: Iterable[float]) -> dict[str, float | int | None]:
    finite = [float(value) for value in values if math.isfinite(float(value))]
    if not finite:
        return {"count": 0, "min": None, "median": None, "p95": None, "max": None}
    return {
        "count": len(finite),
        "min": round(min(finite), 6),
        "median": round(statistics.median(finite), 6),
        "p95": round(_percentile(finite, 0.95) or 0.0, 6),
        "max": round(max(finite), 6),
    }


def rank_metrics(ranks: Sequence[int | None]) -> dict[str, object]:
    if not ranks:
        return {
            "case_count": 0,
            "rank_buckets": {bucket: 0 for bucket in RANK_BUCKETS},
            "rank_11_plus_or_miss_count": 0,
            "recall_at_k": {str(k): None for k in (1, 3, 5, 10)},
            "mrr_at_k": {str(k): None for k in (3, 5, 10)},
            "finite_rank_median": None,
        }
    buckets = Counter(rank_bucket(rank) for rank in ranks)
    finite = [rank for rank in ranks if rank is not None]
    return {
        "case_count": len(ranks),
        "rank_buckets": {bucket: buckets.get(bucket, 0) for bucket in RANK_BUCKETS},
        "rank_11_plus_or_miss_count": sum(rank is None or rank > 10 for rank in ranks),
        "recall_at_k": {
            str(k): round(sum(rank is not None and rank <= k for rank in ranks) / len(ranks), 4)
            for k in (1, 3, 5, 10)
        },
        "mrr_at_k": {
            str(k): round(
                sum(1 / rank for rank in ranks if rank is not None and rank <= k) / len(ranks),
                4,
            )
            for k in (3, 5, 10)
        },
        "finite_rank_median": round(float(statistics.median(finite)), 2) if finite else None,
    }


def aggregate_cross_language_records(records: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Summarize numeric per-case diagnostics without copying any input text/IDs."""
    grouped: dict[str, list[Mapping[str, object]]] = defaultdict(list)
    for record in records:
        direction = record.get("direction")
        rank = record.get("rank")
        if direction not in {"tr_query_to_en_document", "en_query_to_tr_document"}:
            raise ValueError("unsupported cross-language direction")
        if rank is not None and (not isinstance(rank, int) or rank <= 0):
            raise ValueError("rank must be positive or None")
        grouped[str(direction)].append(record)

    result: dict[str, object] = {}
    for direction in ("tr_query_to_en_document", "en_query_to_tr_document"):
        values = grouped.get(direction, [])
        rank_result = rank_metrics([record.get("rank") for record in values])  # type: ignore[arg-type]
        result[direction] = {
            **rank_result,
            "expected_source_cosine": score_distribution(
                float(record["expected_source_score"]) for record in values
            ),
            "top1_cosine": score_distribution(float(record["top1_score"]) for record in values),
            "top1_minus_expected_source": score_distribution(
                float(record["score_margin"]) for record in values
            ),
        }
    return result


def token_count_summary(token_counts: Sequence[int], max_length: int) -> dict[str, int | float | None]:
    if max_length <= 0 or any(count < 0 for count in token_counts):
        raise ValueError("token counts must be non-negative and max_length positive")
    if not token_counts:
        return {"count": 0, "median": None, "p95": None, "maximum": None, "truncated_count": 0}
    return {
        "count": len(token_counts),
        "median": round(float(statistics.median(token_counts)), 2),
        "p95": _percentile([float(count) for count in token_counts], 0.95),
        "maximum": max(token_counts),
        "truncated_count": sum(count > max_length for count in token_counts),
    }
