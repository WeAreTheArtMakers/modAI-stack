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
from app.services.evaluation.models import (
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    RetrievalResult,
    RetrievedEvidence,
    dataset_fingerprint,
)
from app.services.evaluation.runner import AuthorizedRagRetriever, EvaluationRunner, load_dataset
from app.tools.evaluate_rag import _fixture_retriever, _validate_threshold_arguments, _validate_thresholds


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


def test_dataset_fingerprint_is_canonical_and_changes_for_semantic_inputs():
    baseline = dataset()
    reordered = EvaluationDataset.model_validate(json.loads(baseline.model_dump_json()))
    changed_question = baseline.model_copy(
        update={"cases": [baseline.cases[0].model_copy(update={"question": "Different question"}), baseline.cases[1]]}
    )
    changed_fact = baseline.model_copy(
        update={"cases": [baseline.cases[0].model_copy(update={"expected_facts": ["Different fact"]}), baseline.cases[1]]}
    )
    changed_scope = baseline.model_copy(
        update={"cases": [baseline.cases[0].model_copy(update={"knowledge_base_ids": [2]}), baseline.cases[1]]}
    )

    assert dataset_fingerprint(baseline) == dataset_fingerprint(reordered)
    assert dataset_fingerprint(baseline) != dataset_fingerprint(changed_question)
    assert dataset_fingerprint(baseline) != dataset_fingerprint(changed_fact)
    assert dataset_fingerprint(baseline) != dataset_fingerprint(changed_scope)


@pytest.mark.asyncio
async def test_document_id_matching_prevents_duplicate_filename_false_positives_and_keeps_name_fallback():
    duplicate_case = EvaluationCase(
        id="duplicate-name",
        category="technical",
        question="duplicate collision",
        knowledge_base_ids=[1],
        expected_documents=["shared-sentinel.txt"],
        expected_document_ids=[101],
    )

    async def wrong_id(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(
            evidence=[RetrievedEvidence(document="shared-sentinel.txt", document_id=202, chunk_index=0, score=1)]
        )

    async def expected_id(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(
            evidence=[RetrievedEvidence(document="different-visible-name.txt", document_id=101, chunk_index=2, score=1)]
        )

    wrong_result = await EvaluationRunner(wrong_id).run(
        EvaluationDataset(version=1, name="duplicate-id", cases=[duplicate_case]), mode="fixture"
    )
    right_result = await EvaluationRunner(expected_id).run(
        EvaluationDataset(version=1, name="duplicate-id", cases=[duplicate_case]), mode="fixture"
    )
    fallback_case = duplicate_case.model_copy(update={"expected_document_ids": []})
    fallback_result = await EvaluationRunner(wrong_id).run(
        EvaluationDataset(version=1, name="duplicate-name-fallback", cases=[fallback_case]), mode="fixture"
    )

    assert wrong_result.cases[0].source_hit is False
    assert right_result.cases[0].source_hit is True
    assert right_result.cases[0].returned_document_ids == [101]
    assert right_result.cases[0].returned_chunk_indexes == [2]
    assert fallback_result.cases[0].source_hit is True


@pytest.mark.asyncio
async def test_source_accuracy_uses_only_cases_with_expected_source_identity():
    cases = [
        dataset().cases[0],
        EvaluationCase(id="no-source-assertion", category="general", question="status", knowledge_base_ids=[1]),
    ]

    async def retrieve(case: EvaluationCase) -> RetrievalResult:
        if case.id == "case-a":
            return RetrievalResult(
                evidence=[
                    RetrievedEvidence(document="Policy.PDF", score=1),
                    RetrievedEvidence(document="extra.txt", score=0.5),
                ]
            )
        return RetrievalResult(evidence=[RetrievedEvidence(document="not-scored.txt", score=1)])

    result = await EvaluationRunner(retrieve).run(
        EvaluationDataset(version=1, name="denominator", cases=cases), mode="fixture"
    )
    assert result.summary.source_accuracy == 0.5
    assert result.summary.unexpected_source_count == 1


@pytest.mark.asyncio
async def test_top_k_override_is_runtime_only_and_records_effective_metadata():
    original = dataset()
    original_fingerprint = dataset_fingerprint(original)
    observed_top_k: list[int] = []

    async def retrieve(case: EvaluationCase) -> RetrievalResult:
        observed_top_k.append(case.top_k)
        return RetrievalResult(
            evidence=[
                RetrievedEvidence(document="Policy.PDF", score=1),
                RetrievedEvidence(document="extra.txt", score=0.5),
            ]
        )

    result = await EvaluationRunner(retrieve).run(original, mode="fixture", top_k_override=1)

    assert [case.top_k for case in original.cases] == [2, 2]
    assert dataset_fingerprint(original) == original_fingerprint
    assert observed_top_k == [1, 1]
    assert result.dataset_fingerprint == original_fingerprint
    assert result.top_k_override == 1
    assert result.effective_top_k == 1
    assert [case.effective_top_k for case in result.cases] == [1, 1]
    assert result.summary.median_retrieved_source_count == 1.0
    assert result.summary.median_retrieved_chunk_count == 1.0


def test_top_k_override_validation_rejects_invalid_values():
    class Args:
        min_hit_at_k = None
        min_source_accuracy = None
        min_fact_coverage = None
        max_median_total_ms = None
        top_k = 0

    with pytest.raises(ValueError, match="top_k"):
        _validate_threshold_arguments(Args())

    async def retrieve(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult()

    with pytest.raises(ValueError, match="top_k_override"):
        asyncio.run(EvaluationRunner(retrieve).run(dataset(), mode="fixture", top_k_override=51))


@pytest.mark.asyncio
async def test_results_remain_backward_compatible_and_do_not_serialize_sensitive_runtime_content():
    async def retrieve(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(
            evidence=[RetrievedEvidence(document="private.txt", document_id=9, chunk_index=4, score=1, text="source body")],
            prompt="private prompt",
        )

    result = await EvaluationRunner(retrieve).run(
        EvaluationDataset(version=1, name="privacy", cases=[dataset().cases[0]]), mode="fixture"
    )
    serialized = result.model_dump(mode="json")
    text = json.dumps(serialized)
    assert "source body" not in text and "private prompt" not in text
    assert "access_token" not in text and "authorization" not in text

    legacy = json.loads(json.dumps(serialized))
    for field in (
        "dataset_fingerprint",
        "embedding_model",
        "generation_provider",
        "generation_model",
        "rag_top_k_default",
        "effective_top_k",
        "top_k_override",
        "application_version",
        "evaluation_mode",
    ):
        legacy.pop(field)
    for case in legacy["cases"]:
        case.pop("expected_document_ids")
        case.pop("returned_document_ids")
        case.pop("returned_chunk_indexes")
        case.pop("effective_top_k")
        case.pop("retrieved_source_count")
        case.pop("retrieved_chunk_count")
    legacy["summary"].pop("median_retrieved_source_count")
    legacy["summary"].pop("median_retrieved_chunk_count")
    parsed = EvaluationResult.model_validate(legacy)
    assert parsed.dataset_fingerprint is None


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


def test_comparison_warns_when_fingerprints_are_missing_or_different():
    async def retrieve(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(evidence=[])

    baseline = asyncio.run(EvaluationRunner(retrieve).run(dataset(), mode="fixture"))
    changed_dataset = dataset().model_copy(
        update={"cases": [dataset().cases[0].model_copy(update={"expected_facts": ["Changed"]}), dataset().cases[1]]}
    )
    candidate = asyncio.run(EvaluationRunner(retrieve).run(changed_dataset, mode="fixture"))
    comparison = compare_evaluations(baseline, candidate)
    assert "Dataset content differs; aggregate metric deltas are not directly comparable." in comparison.warnings

    legacy = baseline.model_copy(update={"dataset_fingerprint": None})
    legacy_comparison = compare_evaluations(legacy, candidate)
    assert "Dataset fingerprint unavailable; dataset equality cannot be proven for this comparison." in legacy_comparison.warnings


def test_comparison_clearly_reports_effective_top_k_metadata_differences():
    async def retrieve(_case: EvaluationCase) -> RetrievalResult:
        return RetrievalResult(evidence=[RetrievedEvidence(document="Policy.PDF", score=1)])

    baseline = asyncio.run(EvaluationRunner(retrieve).run(dataset(), mode="fixture", top_k_override=5))
    candidate = asyncio.run(EvaluationRunner(retrieve).run(dataset(), mode="fixture", top_k_override=2))
    comparison = compare_evaluations(baseline, candidate)
    assert "Effective top_k differs; retrieval, context, and latency deltas reflect different result counts." in comparison.warnings
    assert "top_k override metadata differs between runs." in comparison.warnings


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
            "--top-k",
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
    payload = json.loads(completed.stdout)
    assert payload["summary"]["hit_at_k"] == 1.0
    assert payload["top_k_override"] == 1
    assert payload["effective_top_k"] == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["cases"][0]["returned_documents"] == ["Policy.PDF"]
    assert json.loads(dataset_path.read_text(encoding="utf-8"))["cases"][0]["top_k"] == 2
