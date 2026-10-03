import asyncio
import json
import sys
import types

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.evaluation.calibration import (
    evaluate_adaptive_candidate,
    select_adaptive_candidate,
    split_calibration_holdout,
)
from app.services.evaluation.models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    RetrievalResult,
    RetrievedEvidence,
)
from app.services.evaluation.quality import (
    compare_reranker_results,
    dataset_quality_summary,
    expected_source_rank_distribution,
    result_quality_summary,
)
from app.services.evaluation.reranker import (
    LocalCrossEncoderReranker,
    RerankerEvaluationError,
    ScoredCandidate,
)
from app.services.evaluation.runner import (
    EvaluationRunner,
    RerankedContextRetriever,
)
from app.services.qdrant import QdrantService


def _case(
    case_id: str,
    *,
    rank: int = 1,
    case_type: str = "normal",
    language: str = "en",
    scenario_id: str | None = None,
    no_answer: bool = False,
    confusable_ids: list[int] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        id=case_id,
        category="security" if language == "tr" else "technical",
        question=f"What is the policy for {case_id}?",
        knowledge_base_ids=[1],
        case_type="no_answer" if no_answer else case_type,
        language=language,
        scenario_id=scenario_id,
        expect_answer=not no_answer,
        expected_document_ids=[] if no_answer else [rank],
        expected_facts=[] if no_answer else [f"fact {case_id}"],
        confusable_document_ids=confusable_ids or [],
        top_k=3,
    )


class _ScoreProvider:
    def __init__(self, order: list[int] | None = None):
        self.order = order
        self.called = False

    async def rerank(self, query, candidates, top_n):
        self.called = True
        indexes = self.order or list(range(len(candidates) - 1, -1, -1))
        selected = [candidates[index] for index in indexes if index < len(candidates)][:top_n]
        return [ScoredCandidate(item, float(len(selected) - rank)) for rank, item in enumerate(selected)]


def test_dataset_schema_supports_explicit_no_answer_and_rejects_ambiguous_cases():
    no_answer = _case("unknown", no_answer=True, confusable_ids=[9])
    assert no_answer.expect_answer is False
    assert no_answer.case_type == "no_answer"

    with pytest.raises(ValidationError, match="expect_answer=false"):
        EvaluationCase(
            id="bad-no-answer",
            question="No evidence?",
            knowledge_base_ids=[1],
            case_type="no_answer",
        )
    with pytest.raises(ValidationError, match="only no_answer"):
        EvaluationCase(
            id="ambiguous",
            question="No evidence?",
            knowledge_base_ids=[1],
            expect_answer=False,
        )
    with pytest.raises(ValidationError, match="cannot declare"):
        EvaluationCase(
            id="bad-labels",
            question="No evidence?",
            knowledge_base_ids=[1],
            case_type="no_answer",
            expect_answer=False,
            expected_facts=["must not exist"],
        )


def test_corpus_quality_summary_is_aggregate_only_and_counts_scenarios():
    dataset = EvaluationDataset(
        version=1,
        name="aggregate-only",
        cases=[
            _case("normal-en", scenario_id="shared"),
            _case("hard-tr", case_type="hard_negative", language="tr", scenario_id="shared"),
            _case("no-answer", no_answer=True, confusable_ids=[8]),
        ],
    )
    report = dataset_quality_summary(dataset)
    assert report["case_count"] == 3
    assert report["category_distribution"] == {"security": 1, "technical": 2}
    assert report["language_distribution"] == {"en": 2, "tr": 1}
    assert report["normal_case_count"] == 1
    assert report["hard_negative_count"] == 1
    assert report["no_answer_count"] == 1
    assert report["access_probe_case_count"] == 0
    assert report["multi_fact_case_count"] == 0
    assert report["near_duplicate_scenario_count"] == 1
    assert "question" not in json.dumps(report)


@pytest.mark.asyncio
async def test_result_quality_summary_is_aggregate_only_and_segments_case_types_and_languages():
    dataset = EvaluationDataset(
        version=1,
        name="private aggregate fixture",
        cases=[
            _case("private-question-normal", rank=1),
            _case("hard-tr", rank=3, case_type="hard_negative", language="tr"),
            _case("private-question-no-answer", no_answer=True, confusable_ids=[8]),
        ],
    )

    async def retrieve(case):
        if case.case_type == "no_answer":
            return RetrievalResult(evidence=[RetrievedEvidence(
                document="private-source.pdf", document_id=8, score=0.8, text="private source body"
            )])
        if case.case_type == "hard_negative":
            return RetrievalResult(evidence=[
                RetrievedEvidence(document="decoy-a.pdf", document_id=91, score=0.9, text="distractor"),
                RetrievedEvidence(document="decoy-b.pdf", document_id=92, score=0.8, text="distractor"),
                RetrievedEvidence(
                    document=f"doc-{case.expected_document_ids[0]}.pdf",
                    document_id=case.expected_document_ids[0], score=0.7, text="private source body fact"
                ),
            ])
        return RetrievalResult(evidence=[RetrievedEvidence(
            document=f"doc-{case.expected_document_ids[0]}.pdf",
            document_id=case.expected_document_ids[0], score=0.9, text="private source body fact"
        )])

    result = await EvaluationRunner(retrieve).run(dataset, mode="fixture")
    report = result_quality_summary(result)
    serialized = json.dumps(report)
    assert report["by_case_type"]["normal"]["hit_at_k"] == 1.0
    assert report["by_case_type"]["hard_negative"]["expected_source_rank_distribution"] == {"3": 1}
    assert report["by_case_type"]["no_answer"]["no_answer_confusable_case_count"] == 1
    assert report["by_language"]["tr"]["case_count"] == 1
    assert "private-question" not in serialized
    assert "private-source" not in serialized
    assert "private source body" not in serialized


def test_calibration_holdout_is_deterministic_and_keeps_scenario_groups_together():
    dataset = EvaluationDataset(
        version=1,
        name="split",
        cases=[
            _case("a1", scenario_id="pair-a"),
            _case("a2", scenario_id="pair-a"),
            _case("b1", scenario_id="pair-b"),
            _case("c1"),
            _case("d1"),
            _case("e1"),
        ],
    )
    calibration, holdout = split_calibration_holdout(dataset, holdout_fraction=0.33)
    again_calibration, again_holdout = split_calibration_holdout(dataset, holdout_fraction=0.33)
    assert [case.id for case in calibration.cases] == [case.id for case in again_calibration.cases]
    assert [case.id for case in holdout.cases] == [case.id for case in again_holdout.cases]
    assert {case.id for case in calibration.cases}.isdisjoint(case.id for case in holdout.cases)
    for scenario in ("pair-a", "pair-b"):
        locations = {
            "calibration" if case in calibration.cases else "holdout"
            for case in dataset.cases
            if case.scenario_id == scenario
        }
        assert len(locations) == 1


def test_adaptive_calibration_selection_uses_calibration_result_then_scores_holdout_separately():
    cases = [
        {
            "case_id": f"cal-{index}",
            "category": "technical",
            "case_type": "normal",
            "language": "en",
            "expect_answer": True,
            "top1_score": 0.9,
            "top2_score": 0.8,
            "top3_score": 0.79,
            "source_hit": True,
            "expected_source_rank": 1,
            "relevant_source_by_rank": [True, False, False],
            "fact_coverage_by_rank": [1.0, 1.0, 1.0],
            "knowledge_base_ids": [1],
            "expected_documents": [],
            "expected_document_ids": [index + 1],
            "returned_documents": [f"doc-{index}.txt"],
            "returned_document_ids": [index + 1],
            "returned_chunk_indexes": [0],
            "no_source_returned": False,
            "expected_fact_count": 1,
            "facts_supported_by_sources": 1,
            "fact_coverage": 1.0,
            "latencies": {"total_ms": 1},
        }
        for index in range(4)
    ]
    calibration = EvaluationResult(
        dataset_version=1,
        dataset_name="calibration",
        summary={"case_count": 4},
        cases=cases,
    )
    holdout = EvaluationResult(
        dataset_version=1,
        dataset_name="holdout",
        summary={"case_count": 2},
        cases=[
            {
                **cases[0],
                "case_id": "hold-1",
                "expected_source_rank": 3,
                "relevant_source_by_rank": [False, False, True],
                "fact_coverage_by_rank": [0.0, 0.0, 1.0],
                "returned_documents": ["wrong1.txt", "wrong2.txt", "doc-0.txt"],
                "returned_document_ids": [91, 92, 1],
            },
            {
                **cases[1],
                "case_id": "hold-2",
                "expected_source_rank": 1,
            },
        ],
    )
    selection = select_adaptive_candidate(calibration, policy="gap")
    holdout_metrics = evaluate_adaptive_candidate(holdout, selection)
    assert selection["selected"] is True
    assert selection["calibration_case_count"] == 4
    assert holdout_metrics is not None
    assert holdout_metrics["case_count"] == 2
    assert holdout_metrics["hit_at_k"] < 1.0


@pytest.mark.asyncio
async def test_reranked_retriever_expands_candidates_then_truncates_final_context_to_three():
    observed_pool_sizes: list[int] = []

    async def retrieve(case):
        observed_pool_sizes.append(case.top_k)
        return RetrievalResult(
            evidence=[
                RetrievedEvidence(
                    document=f"doc-{index}.txt",
                    document_id=index,
                    chunk_index=0,
                    score=1 - index / 100,
                    text=f"private source text {index}",
                )
                for index in range(1, case.top_k + 1)
            ]
        )

    case = _case("rerank", rank=6)
    provider = _ScoreProvider(order=[5, 0, 1, 2, 3, 4])
    wrapped = RerankedContextRetriever(retrieve, provider, candidate_pool_size=6, top_n=3)
    result = await wrapped(case)
    assert observed_pool_sizes == [6]
    assert provider.called
    assert len(result.evidence) == 3
    assert [item.document_id for item in result.evidence] == [6, 1, 2]
    assert [item.vector_rank for item in result.evidence] == [6, 1, 2]
    assert result.candidate_pool_size == 6
    assert result.candidate_expected_document_ranks == [6]
    assert result.prompt is not None and "private source text 6" in result.prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_count", [0, 1, 2, 3, 6])
async def test_reranker_handles_empty_and_small_candidate_sets(candidate_count):
    class FakeModel:
        def predict(self, pairs, **_kwargs):
            return list(range(len(pairs)))

    provider = LocalCrossEncoderReranker("local/fake", model=FakeModel())
    candidates = [
        RetrievedEvidence(document=f"{index}.txt", document_id=index + 1, text=f"text {index}", score=1.0)
        for index in range(candidate_count)
    ]
    reranked = await provider.rerank("question", candidates, 3)
    assert len(reranked) == min(candidate_count, 3)
    assert [item.evidence.document_id for item in reranked] == list(
        range(candidate_count, max(0, candidate_count - 3), -1)
    )


def test_cross_encoder_loading_is_offline_and_disallows_remote_code(monkeypatch, tmp_path):
    captured = {}

    class FakeCrossEncoder:
        def __init__(self, model_name, **kwargs):
            captured["model_name"] = model_name
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "sentence_transformers", types.SimpleNamespace(CrossEncoder=FakeCrossEncoder))
    provider = LocalCrossEncoderReranker("org/model", revision="abc123", cache_dir=tmp_path)
    provider.load()
    assert captured["model_name"] == "org/model"
    assert captured["revision"] == "abc123"
    assert captured["local_files_only"] is True
    assert captured["trust_remote_code"] is False
    assert captured["cache_folder"] == str(tmp_path)


@pytest.mark.asyncio
async def test_reranker_model_failure_is_explicit_and_never_falls_back():
    class BrokenModel:
        def predict(self, _pairs, **_kwargs):
            raise OSError("offline model missing")

    provider = LocalCrossEncoderReranker("local/broken", model=BrokenModel())
    candidate = RetrievedEvidence(document="a.txt", document_id=1, text="source", score=0.5)
    with pytest.raises(RerankerEvaluationError, match="inference failed"):
        await provider.rerank("question", [candidate], 1)


@pytest.mark.asyncio
async def test_reranker_does_not_run_after_authorization_rejection():
    provider = _ScoreProvider()

    async def unauthorized(_case):
        raise HTTPException(status_code=403, detail="Knowledge base access denied")

    wrapped = RerankedContextRetriever(unauthorized, provider, candidate_pool_size=6)
    with pytest.raises(HTTPException, match="denied"):
        await wrapped(_case("cross-tenant"))
    assert provider.called is False


@pytest.mark.asyncio
async def test_authorization_negative_corpus_probe_requires_denial_and_records_no_retrieval():
    probe = EvaluationCase(
        id="foreign-kb-probe",
        category="security",
        question="Can this user search the foreign knowledge base?",
        knowledge_base_ids=[987654],
        case_type="authorization_negative",
        expect_answer=False,
        authorization_expectation="deny",
    )

    async def denied(_case):
        raise HTTPException(status_code=403, detail="Knowledge base access denied")

    result = await EvaluationRunner(denied).run(
        EvaluationDataset(version=1, name="auth-negative", cases=[probe]),
        mode="fixture",
    )
    assert result.cases[0].scope_denied is True
    assert result.summary.access_probe_case_count == 1
    assert result.summary.scope_denial_count == 1
    assert result.summary.no_answer_case_count == 0
    assert result.summary.no_source_count == 0

    async def unexpectedly_allowed(_case):
        return RetrievalResult()

    with pytest.raises(RuntimeError, match="expected authorization denial"):
        await EvaluationRunner(unexpectedly_allowed).run(
            EvaluationDataset(version=1, name="auth-negative", cases=[probe]),
            mode="fixture",
        )


def test_reranker_candidate_pool_configuration_is_validated():
    async def retrieve(_case):
        return RetrievalResult()

    with pytest.raises(ValueError, match="candidate_pool_size"):
        RerankedContextRetriever(retrieve, _ScoreProvider(), candidate_pool_size=2, top_n=3)
    with pytest.raises(ValueError, match="candidate_pool_size"):
        RerankedContextRetriever(retrieve, _ScoreProvider(), candidate_pool_size=51, top_n=3)
    with pytest.raises(ValueError, match="top_n"):
        RerankedContextRetriever(retrieve, _ScoreProvider(), candidate_pool_size=6, top_n=0)


def test_reranker_is_disabled_by_default_and_requires_explicit_candidate_configuration(monkeypatch):
    from app.tools.evaluate_rag import _validate_threshold_arguments, parse_args

    monkeypatch.setattr(sys, "argv", ["evaluate_rag", "--dataset", "private.json"])
    args = parse_args()
    assert args.reranker_model is None
    assert args.reranker_revision is None
    assert args.candidate_pool_size is None
    _validate_threshold_arguments(args)

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "evaluate_rag",
            "--dataset", "private.json",
            "--reranker-model", "org/model",
            "--reranker-revision", "abc123",
            "--candidate-pool-size", "6",
        ],
    )
    args = parse_args()
    assert args.reranker_model == "org/model"
    assert args.reranker_revision == "abc123"
    assert args.candidate_pool_size == 6
    _validate_threshold_arguments(args)

    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_rag", "--dataset", "private.json", "--candidate-pool-size", "6"],
    )
    with pytest.raises(ValueError, match="requires --reranker-model"):
        _validate_threshold_arguments(parse_args())

    monkeypatch.setattr(
        sys,
        "argv",
        ["evaluate_rag", "--dataset", "private.json", "--reranker-revision", "abc123"],
    )
    with pytest.raises(ValueError, match="--reranker-revision requires"):
        _validate_threshold_arguments(parse_args())


@pytest.mark.asyncio
async def test_evaluation_omits_no_answer_generation_and_serializes_no_source_or_prompt_text():
    calls: list[str] = []

    async def retrieve(case):
        return RetrievalResult(
            evidence=[
                RetrievedEvidence(
                    document="confusable.txt",
                    document_id=9,
                    score=0.8,
                    text="private document body",
                )
            ],
            prompt="private prompt text",
        )

    async def generate(_case, _retrieval):
        calls.append("generated")
        return "private generated answer"

    dataset = EvaluationDataset(
        version=1,
        name="no-answer-test",
        cases=[_case("unknown", no_answer=True, confusable_ids=[9])],
    )
    result = await EvaluationRunner(retrieve, generate).run(dataset, mode="fixture")
    serialized = result.model_dump_json()
    assert calls == []
    assert result.cases[0].source_hit is None
    assert result.cases[0].fact_coverage is None
    assert result.cases[0].answer_fact_groundedness is None
    assert result.cases[0].no_answer_confusable_source_count == 1
    assert result.summary.no_answer_case_count == 1
    assert result.summary.no_answer_confusable_case_count == 1
    assert "private document body" not in serialized
    assert "private prompt text" not in serialized
    assert "private generated answer" not in serialized


def test_rank_distribution_and_tenant_scoped_qdrant_filter():
    dataset = EvaluationDataset(
        version=1,
        name="ranks",
        cases=[_case("rank1", rank=1), _case("rank2", rank=2), _case("rank3", rank=3), _case("no-answer", no_answer=True)],
    )
    ranks = [1, 2, 3, None]
    evaluation_cases = []
    for case, rank in zip(dataset.cases, ranks, strict=True):
        answerable = case.expect_answer
        evidence = [
            RetrievedEvidence(
                document=f"doc-{index}.txt",
                document_id=index,
                score=1 - index / 10,
                text=f"fact {case.id}" if index == rank else "unrelated",
            )
            for index in range(1, 4)
        ]
        if not answerable:
            evidence = []
        result = asyncio.run(
            EvaluationRunner(lambda _case, evidence=evidence: _async_result(evidence)).run(
                EvaluationDataset(version=1, name="one", cases=[case]), mode="fixture"
            )
        )
        evaluation_cases.extend(result.cases)
    combined = EvaluationResult(
        dataset_version=1,
        dataset_name="ranks",
        summary={"case_count": len(evaluation_cases)},
        cases=evaluation_cases,
    )
    assert expected_source_rank_distribution(combined) == {
        "rank_1": 1,
        "rank_2": 1,
        "rank_3": 1,
        "missed_by_k3": 0,
        "no_answer": 1,
        "unlabeled_answerable": 0,
        "authorization_negative": 0,
    }

    clauses = QdrantService()._user_filter(
        11,
        organization_id=22,
        workspace_id=33,
        knowledge_base_ids=[44, 55],
    ).must
    assert any(clause.key == "user_id" and clause.match.value == 11 for clause in clauses)
    assert any(clause.key == "organization_id" and clause.match.value == 22 for clause in clauses)
    assert any(clause.key == "workspace_id" and clause.match.value == 33 for clause in clauses)
    assert any(clause.key == "knowledge_base_id" and list(clause.match.any) == [44, 55] for clause in clauses)


async def _async_result(evidence):
    return RetrievalResult(evidence=evidence)


def test_reranker_result_comparison_counts_moves_recoveries_and_harm():
    base_cases = [
        {
            "case_id": "recovered",
            "category": "technical",
            "knowledge_base_ids": [1],
            "expected_documents": [],
            "expected_document_ids": [1],
            "returned_documents": ["wrong.txt", "wrong2.txt", "wrong3.txt"],
            "returned_document_ids": [2, 3, 4],
            "source_hit": False,
            "expected_source_rank": None,
            "expected_document_candidate_ranks": [None],
            "expect_answer": True,
            "case_type": "normal",
            "language": "en",
            "no_source_returned": False,
            "expected_fact_count": 1,
            "facts_supported_by_sources": 0,
            "latencies": {"total_ms": 1},
        },
        {
            "case_id": "harmed",
            "category": "technical",
            "knowledge_base_ids": [1],
            "expected_documents": [],
            "expected_document_ids": [5],
            "returned_documents": ["right.txt"],
            "returned_document_ids": [5],
            "source_hit": True,
            "expected_source_rank": 1,
            "expected_document_candidate_ranks": [1],
            "expect_answer": True,
            "case_type": "normal",
            "language": "en",
            "no_source_returned": False,
            "expected_fact_count": 1,
            "facts_supported_by_sources": 1,
            "latencies": {"total_ms": 1},
        },
    ]
    baseline = EvaluationResult(
        dataset_version=1,
        dataset_name="compare",
        summary={"case_count": 2},
        cases=base_cases,
    )
    candidate_cases = [
        {
            **base_cases[0],
            "returned_documents": ["right.txt", "other.txt"],
            "returned_document_ids": [1, 2],
            "source_hit": True,
            "expected_source_rank": 1,
            "expected_document_candidate_ranks": [6],
        },
        {
            **base_cases[1],
            "returned_documents": ["wrong.txt", "right.txt"],
            "returned_document_ids": [7, 5],
            "source_hit": True,
            "expected_source_rank": 2,
            "expected_document_candidate_ranks": [1],
        },
    ]
    candidate = EvaluationResult(
        dataset_version=1,
        dataset_name="compare",
        summary={"case_count": 2},
        cases=candidate_cases,
    )
    metrics = compare_reranker_results(baseline, candidate)
    assert metrics["previous_k3_misses_recovered"] == 1
    assert metrics["previously_correct_cases_harmed"] == 0
    assert metrics["expected_sources_moved_up"] == 1
    assert metrics["expected_sources_moved_down"] == 1
    assert metrics["expected_sources_missing_from_candidates"] == 0
    assert metrics["rank1_changed_case_count"] == 2
