"""Privacy-safe aggregate summaries for locally held evaluation corpora."""

from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean, median

from app.services.evaluation.models import EvaluationDataset, EvaluationResult, dataset_fingerprint


def dataset_quality_summary(dataset: EvaluationDataset) -> dict[str, object]:
    cases = dataset.cases
    scenario_cases: dict[str, list] = defaultdict(list)
    for case in cases:
        if case.scenario_id:
            scenario_cases[case.scenario_id].append(case)

    fact_distribution = Counter(str(len(case.expected_facts)) for case in cases)
    return {
        "case_count": len(cases),
        "dataset_fingerprint": dataset_fingerprint(dataset),
        "category_distribution": dict(sorted(Counter(case.category for case in cases).items())),
        "language_distribution": dict(sorted(Counter(case.language for case in cases).items())),
        "case_type_distribution": dict(sorted(Counter(case.case_type for case in cases).items())),
        "normal_case_count": sum(case.case_type == "normal" for case in cases),
        "hard_negative_count": sum(case.case_type == "hard_negative" for case in cases),
        "no_answer_count": sum(case.case_type == "no_answer" for case in cases),
        "access_probe_case_count": sum(
            case.case_type == "authorization_negative" for case in cases
        ),
        "multi_fact_case_count": sum(case.expect_answer and len(case.expected_facts) > 1 for case in cases),
        "expected_fact_count_distribution": dict(sorted(fact_distribution.items(), key=lambda item: int(item[0]))),
        "cases_with_confusable_labels": sum(bool(case.confusable_document_ids) for case in cases),
        "shared_scenario_group_count": sum(len(group) > 1 for group in scenario_cases.values()),
        "near_duplicate_scenario_count": sum(
            len(group) > 1 and any(case.case_type == "hard_negative" for case in group)
            for group in scenario_cases.values()
        ),
    }


def expected_source_rank_distribution(
    result: EvaluationResult,
    *,
    max_rank: int = 3,
) -> dict[str, int]:
    if max_rank <= 0:
        raise ValueError("max_rank must be positive")
    distribution = {f"rank_{rank}": 0 for rank in range(1, max_rank + 1)}
    distribution[f"missed_by_k{max_rank}"] = 0
    distribution["no_answer"] = 0
    distribution["unlabeled_answerable"] = 0
    distribution["authorization_negative"] = 0
    for case in result.cases:
        if case.case_type == "authorization_negative":
            distribution["authorization_negative"] += 1
            continue
        if case.case_type == "no_answer":
            distribution["no_answer"] += 1
            continue
        if case.source_hit is None:
            distribution["unlabeled_answerable"] += 1
            continue
        rank = case.expected_source_rank
        if rank is not None and rank <= max_rank:
            distribution[f"rank_{rank}"] += 1
        else:
            distribution[f"missed_by_k{max_rank}"] += 1
    return distribution


def result_quality_summary(result: EvaluationResult) -> dict[str, object]:
    """Summarize outcomes by case type/language without exposing case content."""

    def summarize(cases) -> dict[str, object]:
        answerable = [case for case in cases if case.expect_answer and not case.scope_denied]
        labeled = [case for case in answerable if case.source_hit is not None]
        no_answer = [case for case in cases if case.case_type == "no_answer"]
        access_probes = [case for case in cases if case.case_type == "authorization_negative"]
        latencies = [case.latencies for case in cases if not case.scope_denied]
        retrieved_counts = [case.retrieved_source_count for case in cases if not case.scope_denied]
        return {
            "case_count": len(cases),
            "answerable_case_count": len(answerable),
            "access_probe_count": len(access_probes),
            "scope_denial_count": sum(case.scope_denied for case in access_probes),
            "hit_at_k": mean(case.source_hit for case in labeled) if labeled else None,
            "mean_reciprocal_rank": mean(case.reciprocal_rank or 0.0 for case in labeled) if labeled else None,
            "top1_source_count": sum(case.expected_source_rank == 1 for case in answerable),
            "fact_coverage": mean(
                case.fact_coverage for case in answerable if case.fact_coverage is not None
            ) if any(case.fact_coverage is not None for case in answerable) else None,
            "mean_retrieved_source_count": mean(retrieved_counts) if retrieved_counts else None,
            "median_total_ms": median(case.total_ms for case in latencies) if latencies else None,
            "median_retrieval_ms": median(
                case.retrieval_ms for case in latencies if case.retrieval_ms is not None
            ) if any(case.retrieval_ms is not None for case in latencies) else None,
            "median_reranker_ms": median(
                case.reranker_ms for case in latencies if case.reranker_ms is not None
            ) if any(case.reranker_ms is not None for case in latencies) else None,
            "no_answer_case_count": len(no_answer),
            "no_answer_confusable_case_count": sum(
                case.no_answer_confusable_source_count > 0 for case in no_answer
            ),
            "no_answer_confusable_source_count": sum(
                case.no_answer_confusable_source_count for case in no_answer
            ),
            "expected_source_rank_distribution": dict(sorted(Counter(
                str(case.expected_source_rank or "missed") for case in answerable
            ).items())),
        }

    by_type: dict[str, list] = defaultdict(list)
    by_language: dict[str, list] = defaultdict(list)
    for case in result.cases:
        by_type[case.case_type].append(case)
        by_language[case.language].append(case)
    return {
        "overall": summarize(result.cases),
        "by_case_type": {key: summarize(by_type[key]) for key in sorted(by_type)},
        "by_language": {key: summarize(by_language[key]) for key in sorted(by_language)},
    }


def compare_reranker_results(
    baseline: EvaluationResult,
    candidate: EvaluationResult,
) -> dict[str, int]:
    baseline_by_id = {case.case_id: case for case in baseline.cases}
    candidate_by_id = {case.case_id: case for case in candidate.cases}
    if baseline_by_id.keys() != candidate_by_id.keys():
        raise ValueError("baseline and reranker results must contain identical case IDs")

    expected_sources_up = 0
    expected_sources_down = 0
    rank1_changes = 0
    misses_recovered = 0
    correct_cases_harmed = 0
    expected_sources_missing_from_candidates = 0
    answerable_count = 0
    for case_id, before in baseline_by_id.items():
        after = candidate_by_id[case_id]
        if not before.expect_answer:
            continue
        answerable_count += 1
        vector_ranks = after.expected_document_candidate_ranks
        if after.expected_document_ids:
            final_ranks = [
                next(
                    (
                        rank
                        for rank, document_id in enumerate(after.returned_document_ids, start=1)
                        if document_id == expected_id
                    ),
                    None,
                )
                for expected_id in after.expected_document_ids
            ]
        else:
            final_ranks = [
                next(
                    (
                        rank
                        for rank, document in enumerate(after.returned_documents, start=1)
                        if document.casefold() == expected_name.casefold()
                    ),
                    None,
                )
                for expected_name in after.expected_documents
            ]
        for vector_rank, final_rank in zip(vector_ranks, final_ranks, strict=False):
            if vector_rank is None:
                expected_sources_missing_from_candidates += 1
                continue
            if final_rank is None:
                expected_sources_down += 1
            else:
                expected_sources_up += final_rank < vector_rank
                expected_sources_down += final_rank > vector_rank

        if (before.returned_document_ids[:1] or before.returned_documents[:1]) != (
            after.returned_document_ids[:1] or after.returned_documents[:1]
        ):
            rank1_changes += 1
        if before.source_hit is False and after.source_hit is True:
            misses_recovered += 1
        if before.source_hit is True and after.source_hit is False:
            correct_cases_harmed += 1

    return {
        "answerable_case_count": answerable_count,
        "expected_sources_moved_up": expected_sources_up,
        "expected_sources_moved_down": expected_sources_down,
        "rank1_changed_case_count": rank1_changes,
        "previous_k3_misses_recovered": misses_recovered,
        "previously_correct_cases_harmed": correct_cases_harmed,
        "expected_sources_missing_from_candidates": expected_sources_missing_from_candidates,
    }
