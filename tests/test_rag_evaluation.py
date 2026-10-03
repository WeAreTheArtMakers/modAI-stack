import asyncio
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.services.evaluation.comparison import compare_evaluations
from app.services.evaluation.metrics import answer_fact_groundedness, fact_coverage, normalize_text
from app.services.evaluation.models import EvaluationCase, EvaluationDataset, RetrievalResult, RetrievedEvidence
from app.services.evaluation.runner import AuthorizedRagRetriever, EvaluationRunner, load_dataset
from app.tools.evaluate_rag import _fixture_retriever, _validate_thresholds


def dataset() -> EvaluationDataset:
    return EvaluationDataset.model_validate(
        {
            "version": 1,
            "name": "quality-fixture",
            "cases": [
                {
                    "id": "case-a",
                    "category": "technical",
                    "question": "What is the retention period?",
                    "knowledge_base_ids": [1],
                    "expected_documents": ["Policy.PDF"],
                    "expected_facts": ["Retention is 24 months"],
                    "top_k": 2,
                },
                {
                    "id": "case-b",
                    "category": "policy",
                    "question": "Who approves onboarding?",
                    "knowledge_base_ids": [1],
                    "expected_documents": ["Onboarding.docx"],
                    "expected_facts": ["Manager approval is required"],
                    "top_k": 2,
                },
            ],
        }
    )


@pytest.mark.asyncio
async def test_runner_reports_deterministic_retrieval_source_fact_and_latency_metrics():
    async def retrieve(case: EvaluationCase) -> RetrievalResult:
        if case.id == "case-a":
            return RetrievalResult(
                evidence=[
                    RetrievedEvidence(document="irrelevant.txt", score=0.9, text="unrelated"),
                    RetrievedEvidence(document="policy.pdf", score=0.8, text="Retention is 24 months."),
                ],
                embedding_latency_ms=3,
                retrieval_latency_ms=7,
            )
        return RetrievalResult(evidence=[], embedding_latency_ms=5, retrieval_latency_ms=11)

    result = await EvaluationRunner(retrieve).run(dataset(), mode="fixture", models={"embedding_model": "e1", "generation_model": None})

    first, second = result.cases
    assert first.source_hit is True
    assert first.reciprocal_rank == 0.5
    assert first.unexpected_sources == ["irrelevant.txt"]
    assert first.fact_coverage == 1.0
    assert second.source_hit is False and second.no_source_returned is True
    assert result.summary.hit_at_k == 0.5
    assert result.summary.mean_reciprocal_rank == 0.25
    assert result.summary.source_accuracy == 0.5
    assert result.summary.unexpected_source_count == 1
    assert result.summary.no_source_count == 1
    assert result.summary.fact_coverage == 0.5
    serialized = result.model_dump(mode="json")
    assert "Retention is 24 months." not in json.dumps(serialized)
    assert "prompt" not in json.dumps(serialized)


@pytest.mark.asyncio
async def test_groundedness_requires_a_fact_in_both_answer_and_retrieved_context():
    async def retrieve(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(evidence=[RetrievedEvidence(document="policy.pdf", score=1, text="Retention is 24 months")])

    async def generate(_case: EvaluationCase, _result: RetrievalResult) -> str:
        return "The retention is 24 months."

    result = await EvaluationRunner(retrieve, generate).run(dataset().model_copy(update={"cases": [dataset().cases[0]]}), mode="fixture")
    assert result.cases[0].answer_fact_groundedness == 1.0
    assert answer_fact_groundedness(["fact"], ["fact"], None) is None


def test_dataset_validation_rejects_invalid_versions_ids_questions_scopes_and_categories(tmp_path: Path):
    invalid = dataset().model_dump()
    invalid["version"] = 2
    with pytest.raises(ValidationError):
        EvaluationDataset.model_validate(invalid)

    invalid = dataset().model_dump()
    invalid["cases"][1]["id"] = "case-a"
    with pytest.raises(ValidationError, match="unique"):
        EvaluationDataset.model_validate(invalid)

    invalid = dataset().model_dump()
    invalid["cases"][0]["question"] = "  "
    with pytest.raises(ValidationError):
        EvaluationDataset.model_validate(invalid)

    invalid = dataset().model_dump()
    invalid["cases"][0]["knowledge_base_ids"] = [1, 1]
    with pytest.raises(ValidationError, match="duplicates"):
        EvaluationDataset.model_validate(invalid)

    invalid = dataset().model_dump()
    invalid["cases"][0]["category"] = "unknown"
    with pytest.raises(ValidationError, match="must be one of"):
        EvaluationDataset.model_validate(invalid)

    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid evaluation dataset"):
        load_dataset(path)


def test_text_normalization_is_unicode_case_and_whitespace_safe():
    assert normalize_text("  İSTANBUL\u00a0  POLICY ") == normalize_text("i̇stanbul policy")
    assert fact_coverage(["Yönetici onayı gereklidir"], ["YÖNETİCİ   onayı gereklidir."]) == 1.0


@pytest.mark.asyncio
async def test_fixture_retriever_and_explicit_thresholds(tmp_path: Path):
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(
        json.dumps({"case-a": [{"document": "Policy.PDF", "score": 1.0, "text": "Retention is 24 months"}]}),
        encoding="utf-8",
    )
    result = await EvaluationRunner(_fixture_retriever(str(fixture_path))).run(
        dataset().model_copy(update={"cases": [dataset().cases[0]]}), mode="fixture"
    )

    class Args:
        min_hit_at_k = 1.0
        min_source_accuracy = 1.0
        min_fact_coverage = 1.0
        max_median_total_ms = None

    assert _validate_thresholds(Args(), result) == []
    Args.min_fact_coverage = 1.1
    assert "fact coverage" in _validate_thresholds(Args(), result)[0]


def test_comparison_reports_objective_deltas_and_embedding_model_warning():
    async def retrieve(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(evidence=[])

    baseline = asyncio.run(EvaluationRunner(retrieve).run(dataset(), mode="fixture", models={"embedding_model": "old", "generation_model": "g"}))
    candidate = asyncio.run(EvaluationRunner(retrieve).run(dataset(), mode="fixture", models={"embedding_model": "new", "generation_model": "g"}))
    comparison = compare_evaluations(baseline, candidate)
    assert comparison.deltas["hit_at_k"] == 0.0
    assert comparison.warnings == ["Embedding model changed; reindex knowledge bases before treating retrieval deltas as comparable."]


@pytest.mark.asyncio
async def test_authorized_retriever_never_calls_rag_for_an_unauthorized_knowledge_base(monkeypatch):
    async def reject_scope(_db, _user, knowledge_base_ids):
        assert knowledge_base_ids == [99]
        raise HTTPException(403, "Knowledge base access denied")

    async def unexpected_rag(**_kwargs):
        raise AssertionError("RAG retrieval must not run after authorization is rejected")

    monkeypatch.setattr("app.services.evaluation.runner.resolve_knowledge_base_scope", reject_scope)
    monkeypatch.setattr("app.services.evaluation.runner.retrieve_rag_context", unexpected_rag)
    case = EvaluationCase(
        id="foreign-tenant",
        category="technical",
        question="secret",
        knowledge_base_ids=[99],
    )
    with pytest.raises(HTTPException, match="denied"):
        await AuthorizedRagRetriever(object(), {"sub": "7"})(case)


def test_evaluation_cli_runs_deterministically_without_models(tmp_path: Path):
    dataset_path = tmp_path / "dataset.json"
    fixture_path = tmp_path / "fixture.json"
    output_path = tmp_path / "result.json"
    dataset_path.write_text(dataset().model_dump_json(), encoding="utf-8")
    fixture_path.write_text(
        json.dumps(
            {
                "case-a": [{"document": "Policy.PDF", "score": 1.0, "text": "Retention is 24 months"}],
                "case-b": [{"document": "Onboarding.docx", "score": 1.0, "text": "Manager approval is required"}],
            }
        ),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.tools.evaluate_rag",
            "--dataset",
            str(dataset_path),
            "--mode",
            "fixture",
            "--fixture",
            str(fixture_path),
            "--min-hit-at-k",
            "1",
            "--output",
            str(output_path),
            "--json",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert json.loads(completed.stdout)["summary"]["hit_at_k"] == 1.0
    assert json.loads(output_path.read_text(encoding="utf-8"))["cases"][0]["returned_documents"] == ["Policy.PDF"]
