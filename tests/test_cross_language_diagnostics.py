import json
from pathlib import Path

import pytest

from app.services.evaluation.cross_language_diagnostics import (
    aggregate_cross_language_records,
    rank_bucket,
    rank_metrics,
    score_distribution,
    token_count_summary,
)
from app.tools.diagnose_cross_language_retrieval import (
    _direction,
    audit_canonical_directionality,
)
from app.core.config import Settings
from app.services.evaluation.embedding_profiles import MINILM_BASELINE, MULTILINGUAL_E5_SMALL
from evaluation.corpora.cross_language_mirror_v1.generator import build_corpus


def test_rank_buckets_recall_and_truncated_mrr_are_deterministic():
    ranks = [1, 2, 3, 4, 5, 6, 10, 11, 20, None]

    assert [rank_bucket(rank) for rank in ranks] == [
        "1", "2", "3", "4-5", "4-5", "6-10", "6-10", "11-20", "11-20", ">20/miss"
    ]
    result = rank_metrics(ranks)
    assert result["rank_11_plus_or_miss_count"] == 3
    assert result["recall_at_k"] == {"1": 0.1, "3": 0.3, "5": 0.5, "10": 0.7}
    assert result["mrr_at_k"] == {"3": 0.1833, "5": 0.2283, "10": 0.255}
    with pytest.raises(ValueError, match="positive"):
        rank_bucket(0)


def test_score_and_token_summaries_are_aggregate_only():
    assert score_distribution([0.2, 0.4, 0.6, 0.8]) == {
        "count": 4, "min": 0.2, "median": 0.5, "p95": 0.8, "max": 0.8
    }
    assert token_count_summary([1, 3, 5, 8], max_length=5) == {
        "count": 4, "median": 4.0, "p95": 8.0, "maximum": 8, "truncated_count": 1
    }


def test_cross_language_aggregate_drops_case_questions_and_document_text():
    records = [
        {
            "direction": "tr_query_to_en_document", "rank": 4,
            "expected_source_score": 0.61, "top1_score": 0.72, "score_margin": 0.11,
            "question": "SYNTHETIC PRIVATE QUESTION SENTINEL",
            "document_text": "SYNTHETIC PRIVATE DOCUMENT SENTINEL",
            "case_id": "fictional-case-id",
        },
        {
            "direction": "en_query_to_tr_document", "rank": None,
            "expected_source_score": 0.33, "top1_score": 0.78, "score_margin": 0.45,
            "question": "ANOTHER SYNTHETIC QUESTION SENTINEL",
            "document_text": "ANOTHER SYNTHETIC DOCUMENT SENTINEL",
        },
    ]

    serialized = json.dumps(aggregate_cross_language_records(records), sort_keys=True)
    for sentinel in (
        "SYNTHETIC PRIVATE QUESTION SENTINEL",
        "SYNTHETIC PRIVATE DOCUMENT SENTINEL",
        "ANOTHER SYNTHETIC QUESTION SENTINEL",
        "ANOTHER SYNTHETIC DOCUMENT SENTINEL",
        "fictional-case-id",
    ):
        assert sentinel not in serialized


def test_mirrored_corpus_is_deterministic_fingerprinted_and_directionally_balanced():
    from app.services.evaluation.synthetic_corpus import corpus_fingerprint

    docs_a, dataset_a, manifest_a = build_corpus()
    docs_b, dataset_b, manifest_b = build_corpus()

    assert docs_a == docs_b
    assert dataset_a.model_dump(mode="json") == dataset_b.model_dump(mode="json")
    assert manifest_a == manifest_b
    assert manifest_a["fingerprint_sha256"] == (
        "95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833595e188c"
    )
    assert corpus_fingerprint("cross-language-mirror-v1", dataset_a, docs_a["documents"]) == manifest_a[
        "fingerprint_sha256"
    ]
    assert manifest_a["document_count"] == 40
    assert manifest_a["case_count"] == 40
    assert manifest_a["mirrored_fact_pair_count"] == 20
    assert manifest_a["directional_case_counts"] == {
        "tr_query_to_en_document": 20,
        "en_query_to_tr_document": 20,
    }


def test_mirrored_cases_share_fact_pairs_and_preserve_turkish_unicode():
    documents_payload, dataset, _ = build_corpus()
    documents = {item["document_id"]: item for item in documents_payload["documents"]}
    directions = {"tr_query_to_en_document": [], "en_query_to_tr_document": []}
    cases_by_scenario = {}
    for case in dataset.cases:
        cases_by_scenario.setdefault(case.scenario_id, []).append(case)
        source_language = documents[case.expected_document_ids[0]]["language"]
        direction = (
            "tr_query_to_en_document"
            if case.language == "tr" and source_language == "en"
            else "en_query_to_tr_document"
        )
        directions[direction].append(case)

    assert len(directions["tr_query_to_en_document"]) == 20
    assert len(directions["en_query_to_tr_document"]) == 20
    assert len(cases_by_scenario) == 20
    for pair in cases_by_scenario.values():
        assert len(pair) == 2
        assert {case.language for case in pair} == {"en", "tr"}
        assert pair[0].scenario_id == pair[1].scenario_id
        assert pair[0].expected_document_ids[0] in pair[1].confusable_document_ids
        assert pair[1].expected_document_ids[0] in pair[0].confusable_document_ids

    all_turkish = " ".join(
        [item["text"] for item in documents_payload["documents"]]
        + [case.question for case in dataset.cases if case.language == "tr"]
    )
    assert all(character in all_turkish for character in "ıİğşçöü")


def test_canonical_directionality_audit_reports_structure_without_raw_text():
    root = Path(__file__).resolve().parents[1]
    raw_dataset = json.loads(
        (root / "evaluation/corpora/compact-multilingual-v1/dataset.json").read_text(encoding="utf-8")
    )
    raw_documents = json.loads(
        (root / "evaluation/corpora/compact-multilingual-v1/documents.json").read_text(encoding="utf-8")
    )
    from app.services.evaluation.models import EvaluationDataset

    result = audit_canonical_directionality(
        EvaluationDataset.model_validate(raw_dataset), raw_documents["documents"]
    )
    assert result["tr_query_to_en_document"]["case_count"] == 22
    assert result["en_query_to_tr_document"]["case_count"] == 22
    for values in result.values():
        assert values["unique_expected_source_count"] == 22
        assert values["case_type_counts"] == {"normal": 22, "hard_negative": 0, "no_answer": 0}
        assert values["numeric_expected_fact_count"] == 22
        assert values["policy_version_source_count"] == 2
        assert sum(values["query_template_distribution"].values()) == 22
        assert "shared_non_numeric_query_source_terms" in values
    serialized = json.dumps(result, sort_keys=True)
    assert "annual leave" not in serialized.lower()
    assert "synthetic-" not in serialized


def test_direction_labels_and_default_production_retrieval_are_unchanged():
    documents_payload, dataset, _ = build_corpus()
    documents_by_id = {
        item["document_id"]: item for item in documents_payload["documents"]
    }
    labels = {
        _direction(case, documents_by_id)
        for case in dataset.cases
    }
    assert labels == {"tr_query_to_en_document", "en_query_to_tr_document"}

    production_defaults = Settings(_env_file=None)
    assert production_defaults.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert production_defaults.rag_top_k == 3


def test_model_prefix_contract_preserves_turkish_unicode_without_double_prefixing():
    text = "İzin süresi; ı, ğ, ş, ç, ö, ü"
    assert MINILM_BASELINE.preprocess_query(text) == text
    assert MINILM_BASELINE.preprocess_passage(text) == text
    query = MULTILINGUAL_E5_SMALL.preprocess_query(text)
    passage = MULTILINGUAL_E5_SMALL.preprocess_passage(text)
    assert query == f"query: {text}"
    assert passage == f"passage: {text}"
    assert query.count("query: ") == 1
    assert passage.count("passage: ") == 1
