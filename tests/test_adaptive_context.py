import json

import pytest

from app.services.evaluation.adaptive import (
    adaptive_context_k,
    retrieval_score_features,
    summarize_adaptive_policy,
)
from app.services.evaluation.models import (
    EvaluationCase,
    EvaluationDataset,
    RetrievalResult,
    RetrievedEvidence,
    dataset_fingerprint,
)
from app.services.evaluation.runner import AdaptiveContextRetriever, EvaluationRunner


def test_retrieval_score_features_calculate_gaps_and_positive_ratios():
    features = retrieval_score_features([0.9, 0.8, 0.6])
    assert features.top1_score == 0.9
    assert features.top2_score == 0.8
    assert features.top3_score == 0.6
    assert features.score_gap_1_2 == pytest.approx(0.1)
    assert features.score_gap_2_3 == pytest.approx(0.2)
    assert features.score_ratio_2_1 == pytest.approx(0.8 / 0.9)
    assert features.score_ratio_3_1 == pytest.approx(0.6 / 0.9)
    assert features.score_ratio_3_2 == pytest.approx(0.75)


def test_ratios_are_undefined_for_missing_or_nonpositive_denominators():
    assert retrieval_score_features([]).score_gap_2_3 is None
    assert retrieval_score_features([0.9]).score_ratio_2_1 is None
    features = retrieval_score_features([0.0, -0.1, -0.2])
    assert features.score_ratio_2_1 is None
    assert features.score_ratio_3_1 is None
    assert features.score_ratio_3_2 is None


@pytest.mark.parametrize(
    ("scores", "policy", "threshold", "expected"),
    [
        ([], "gap", 0.1, 0),
        ([0.9], "gap", 0.1, 1),
        ([0.9, 0.8], "gap", 0.1, 2),
        ([0.875, 0.75, 0.5], "gap", 0.24, 2),
        ([0.875, 0.75, 0.5], "gap", 0.25, 3),
        ([0.9, 0.8, 0.6], "ratio", 0.74, 3),
        ([0.9, 0.8, 0.6], "ratio", 0.76, 2),
        ([0.95, 0.7, 0.68], "three_tier", 0.05, 1),
        ([0.8, 0.7, 0.68], "three_tier", 0.05, 3),
    ],
)
def test_adaptive_policy_selection_and_threshold_boundaries(scores, policy, threshold, expected):
    second_threshold = 0.2 if policy == "three_tier" else None
    assert adaptive_context_k(
        scores,
        policy=policy,
        threshold=threshold,
        second_threshold=second_threshold,
    ) == expected


def test_three_tier_requires_second_threshold():
    with pytest.raises(ValueError, match="second_threshold"):
        adaptive_context_k([0.9, 0.8, 0.7], policy="three_tier", threshold=0.2)


def test_adaptive_thresholds_must_be_finite():
    with pytest.raises(ValueError, match="finite"):
        adaptive_context_k([0.9, 0.8, 0.7], policy="gap", threshold=float("nan"))


@pytest.mark.asyncio
async def test_evaluation_persists_only_numeric_score_metadata_and_keeps_fingerprint():
    authored = EvaluationDataset(
        version=1,
        name="adaptive-metadata-fixture",
        cases=[
            EvaluationCase(
                id="case-a",
                category="technical",
                question="Which policy applies?",
                knowledge_base_ids=[4],
                expected_documents=["policy.pdf"],
                expected_facts=["approval is required"],
                top_k=3,
            )
        ],
    )
    fingerprint_before = dataset_fingerprint(authored)

    async def retrieve(_case):
        return RetrievalResult(
            evidence=[
                RetrievedEvidence(document="policy.pdf", score=0.9, text="approval is required"),
                RetrievedEvidence(document="extra.txt", score=0.8, text="other source text"),
                RetrievedEvidence(document="third.txt", score=0.6, text="third source text"),
            ]
        )

    result = await EvaluationRunner(retrieve).run(authored, mode="fixture")
    case = result.cases[0]
    serialized = json.dumps(result.model_dump(mode="json"))
    assert case.expected_source_rank == 1
    assert case.relevant_source_by_rank == [True, False, False]
    assert case.fact_coverage_by_rank == [1.0, 1.0, 1.0]
    assert case.score_gap_2_3 == pytest.approx(0.2)
    assert "approval is required" not in serialized
    assert "other source text" not in serialized
    assert "third source text" not in serialized
    assert dataset_fingerprint(authored) == fingerprint_before


@pytest.mark.asyncio
async def test_adaptive_retriever_selects_prefix_but_keeps_all_numeric_score_features():
    authored = EvaluationDataset(
        version=1,
        name="adaptive-wrapper-fixture",
        cases=[
            EvaluationCase(
                id="case-a",
                category="technical",
                question="Which policy applies?",
                knowledge_base_ids=[4],
                expected_documents=["policy.pdf"],
                expected_facts=[],
                top_k=3,
            )
        ],
    )

    async def retrieve(_case):
        return RetrievalResult(
            evidence=[
                RetrievedEvidence(document="first.pdf", score=0.9, text="first source text"),
                RetrievedEvidence(document="second.pdf", score=0.8, text="second source text"),
                RetrievedEvidence(document="third.pdf", score=0.79, text="third source text"),
            ],
            retrieval_scores=[0.9, 0.8, 0.79],
        )

    adaptive = AdaptiveContextRetriever(retrieve, policy="gap", threshold=0.005)
    result = await EvaluationRunner(adaptive).run(authored, mode="fixture")
    case = result.cases[0]
    assert case.retrieved_source_count == 2
    assert case.top3_score == pytest.approx(0.79)
    assert case.score_gap_2_3 == pytest.approx(0.01)
    serialized = json.dumps(result.model_dump(mode="json"))
    assert "third source text" not in serialized
    assert "second source text" not in serialized


def test_policy_summary_reports_quality_and_context_distribution():
    cases = [
        {
            "top1_score": 0.9,
            "top2_score": 0.8,
            "top3_score": 0.6,
            "source_hit": True,
            "expected_source_rank": 1,
            "relevant_source_by_rank": [True, False, False],
            "fact_coverage_by_rank": [1.0, 1.0, 1.0],
        },
        {
            "top1_score": 0.9,
            "top2_score": 0.8,
            "top3_score": 0.79,
            "source_hit": True,
            "expected_source_rank": 3,
            "relevant_source_by_rank": [False, False, True],
            "fact_coverage_by_rank": [0.0, 0.0, 1.0],
        },
    ]
    metrics = summarize_adaptive_policy(cases, policy="gap", threshold=0.02)
    assert metrics["hit_at_k"] == 1.0
    assert metrics["mean_reciprocal_rank"] == pytest.approx(2 / 3)
    assert metrics["fact_coverage"] == 1.0
    assert metrics["source_accuracy"] == pytest.approx(2 / 5)
    assert metrics["mean_source_count"] == 2.5
    assert metrics["median_source_count"] == 2.5
    assert metrics["source_count_distribution"] == {0: 0, 1: 0, 2: 1, 3: 1}
