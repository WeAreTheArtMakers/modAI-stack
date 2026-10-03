import json

from app.services.evaluation.synthetic_corpus import corpus_fingerprint
from evaluation.corpora.compact_multilingual_v1.generator import (
    CORPUS_VERSION,
    build_corpus,
    write_corpus,
)


EXPECTED_FINGERPRINT = "81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b"


def test_compact_multilingual_corpus_is_deterministic_and_versioned():
    documents_a, dataset_a, manifest_a = build_corpus()
    documents_b, dataset_b, manifest_b = build_corpus()

    fingerprint_a = corpus_fingerprint(
        documents_a["corpus_version"], dataset_a, documents_a["documents"]
    )
    fingerprint_b = corpus_fingerprint(
        documents_b["corpus_version"], dataset_b, documents_b["documents"]
    )
    assert CORPUS_VERSION == "compact-multilingual-v1"
    assert fingerprint_a == fingerprint_b == EXPECTED_FINGERPRINT
    assert manifest_a == manifest_b
    assert manifest_a["fingerprint_sha256"] == EXPECTED_FINGERPRINT


def test_generated_files_match_canonical_dataset_fingerprint(tmp_path):
    manifest = write_corpus(tmp_path)
    documents = json.loads((tmp_path / "documents.json").read_text(encoding="utf-8"))
    dataset = json.loads((tmp_path / "dataset.json").read_text(encoding="utf-8"))
    from app.services.evaluation.models import EvaluationDataset

    fingerprint = corpus_fingerprint(
        documents["corpus_version"],
        EvaluationDataset.model_validate(dataset),
        documents["documents"],
    )
    assert fingerprint == manifest["fingerprint_sha256"] == EXPECTED_FINGERPRINT


def test_corpus_has_balanced_languages_cross_language_pairs_and_no_answer_cases():
    documents, dataset, manifest = build_corpus()
    document_by_id = {doc["document_id"]: doc for doc in documents["documents"]}
    answerable = [case for case in dataset.cases if case.expect_answer]
    no_answer = [case for case in dataset.cases if case.case_type == "no_answer"]

    assert len(documents["documents"]) == 44
    assert len(answerable) == 132
    assert len(no_answer) == 24
    assert sum(case.language == "en" for case in answerable) == 66
    assert sum(case.language == "tr" for case in answerable) == 66
    assert sum(case.language == "en" for case in no_answer) == 12
    assert sum(case.language == "tr" for case in no_answer) == 12
    assert manifest["cross_language_case_counts"] == {
        "tr_query_to_en_document": 22,
        "en_query_to_tr_document": 22,
    }
    assert all(case.top_k == 3 for case in dataset.cases)
    assert all(case.knowledge_base_ids == [1] for case in dataset.cases)
    assert all(doc["filename"].startswith("synthetic-") for doc in documents["documents"])

    cross_tr_en = [
        case for case in answerable
        if case.language == "tr" and document_by_id[case.expected_document_ids[0]]["language"] == "en"
    ]
    cross_en_tr = [
        case for case in answerable
        if case.language == "en" and document_by_id[case.expected_document_ids[0]]["language"] == "tr"
    ]
    assert len(cross_tr_en) == len(cross_en_tr) == 22


def test_hard_negative_cases_have_same_family_confusables_and_distinct_answers():
    documents, dataset, _ = build_corpus()
    doc_ids = {doc["document_id"] for doc in documents["documents"]}
    hard_negatives = [case for case in dataset.cases if case.case_type == "hard_negative"]

    assert len(hard_negatives) == 44
    for case in hard_negatives:
        assert case.expected_document_ids[0] in doc_ids
        assert case.confusable_document_ids
        assert not set(case.expected_document_ids).intersection(case.confusable_document_ids)
        assert set(case.confusable_document_ids).issubset(doc_ids)


def test_all_benchmark_material_is_synthetic_and_avoids_contacts_or_credentials():
    documents, dataset, _ = build_corpus()
    serialized = json.dumps(
        {
            "documents": documents,
            "cases": [case.model_dump(mode="json") for case in dataset.cases],
        },
        ensure_ascii=False,
    )
    lowered = serialized.lower()
    assert "@" not in serialized
    assert "password=" not in lowered
    assert "api_key=" not in lowered
    assert "bearer " not in lowered
    assert "customer name" not in lowered
