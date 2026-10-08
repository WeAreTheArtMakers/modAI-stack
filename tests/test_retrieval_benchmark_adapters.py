import hashlib
import json
import shutil
from collections import Counter

import pytest

from benchmarks.retrieval.adapters import (
    COMPACT_MULTILINGUAL_V1,
    CROSS_LANGUAGE_MIRROR_V1,
    REPOSITORY_ROOT,
    LegacyAdapterError,
    adapt_legacy_corpus,
)
from benchmarks.retrieval.schema import (
    DatasetValidationError,
    assess_dataset,
    dataset_fingerprints_v2,
    validate_dataset_v2,
)


ADAPTED_DATASET_SHA256 = {
    "compact-multilingual-v1": "f47c4d7dd3b6e8980a2e32250d4e0b8db0772e8fc709387a22091023f473959c",
    "cross-language-mirror-v1": "c63a9e0b312990aff84c5da6851b57aaa8852cd275945b0539558dd19230ce5b",
}


def _source_hashes(spec):
    directory = REPOSITORY_ROOT / "evaluation" / "corpora" / spec.corpus_version
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(directory.glob("*.json"))}


def test_compact_adapter_preserves_expected_sources_and_confusables_unjudged():
    dataset, report = adapt_legacy_corpus(COMPACT_MULTILINGUAL_V1)
    assert (report.document_count, report.query_count, report.answerable_query_count) == (44, 156, 132)
    assert report.expected_source_relationships == 132
    assert report.historical_confusable_relationships == 492
    assert report.direction_counts == {"same_language": 88, "tr_to_en": 22, "en_to_tr": 22, "not_applicable": 24}
    assert Counter(query.primary_category for query in dataset.queries) == {
        "single_document_fact": 44,
        "semantic_distractor": 44,
        "cross_lingual": 44,
        "unanswerable": 24,
    }
    assert len({query.scenario_id for query in dataset.queries}) == 56
    assessment = assess_dataset(dataset)
    assert assessment.judgment_grade_counts == {0: 0, 1: 0, 2: 132}
    assert assessment.unjudged_historical_relationship_count == 492
    assert assessment.real_world_benchmark_status == "NOT YET ESTABLISHED"
    assert sum(len(query.historical_relationships) for query in dataset.queries if not query.answerable) == 96
    assert dataset_fingerprints_v2(dataset).dataset_sha256 == ADAPTED_DATASET_SHA256["compact-multilingual-v1"]


def test_mirror_adapter_keeps_translation_confusables_unjudged_and_flags_incomplete_groups():
    dataset, report = adapt_legacy_corpus(CROSS_LANGUAGE_MIRROR_V1)
    assert (report.document_count, report.query_count) == (40, 40)
    assert report.direction_counts == {"tr_to_en": 20, "en_to_tr": 20}
    assert report.historical_confusable_relationships == 40
    assert "required_groups_may_be_incomplete" in dataset.legacy_source.limitations
    assert all(document.translation_group_id is None for document in dataset.documents)
    assert all(len(query.required_groups) == 1 and len(query.required_groups[0].members) == 1 for query in dataset.queries)
    assert assess_dataset(dataset).judgment_grade_counts == {0: 0, 1: 0, 2: 40}
    assert dataset_fingerprints_v2(dataset).dataset_sha256 == ADAPTED_DATASET_SHA256["cross-language-mirror-v1"]


@pytest.mark.parametrize("spec", [COMPACT_MULTILINGUAL_V1, CROSS_LANGUAGE_MIRROR_V1], ids=lambda spec: spec.corpus_version)
def test_adapted_datasets_are_synthetic_stress_without_fabricated_evidence(spec):
    dataset, report = adapt_legacy_corpus(spec)
    assert dataset.lane == "synthetic_stress"
    assert dataset.evidence_labels == "unavailable"
    assert dataset.legacy_source.legacy_corpus_sha256 == spec.corpus_sha256
    assert dataset.legacy_source.legacy_dataset_sha256 == spec.dataset_sha256
    assert tuple(dataset.legacy_source.limitations) == spec.limitations == report.limitations
    assert {query.review.status for query in dataset.queries} == {"generator_labeled"}
    for query in dataset.queries:
        assert all(judgment.basis == "legacy_expected_source" and not judgment.evidence for judgment in query.judgments)
        for relationship in query.historical_relationships:
            assert relationship.legacy_corpus_version == spec.corpus_version
            assert relationship.legacy_case_id == query.query_id
            assert relationship.document_id == f"doc-{relationship.legacy_document_id:03d}"
    assert {document.provenance.source_class for document in dataset.documents} == {"synthetic_generated"}


@pytest.mark.parametrize("spec", [COMPACT_MULTILINGUAL_V1, CROSS_LANGUAGE_MIRROR_V1], ids=lambda spec: spec.corpus_version)
def test_adapter_is_read_only_and_deterministic(spec):
    before = _source_hashes(spec)
    first, _ = adapt_legacy_corpus(spec)
    second, _ = adapt_legacy_corpus(spec)
    assert _source_hashes(spec) == before
    assert dataset_fingerprints_v2(first) == dataset_fingerprints_v2(second)


def test_adapter_rejects_tampered_corpus_text(tmp_path):
    source = REPOSITORY_ROOT / "evaluation" / "corpora" / COMPACT_MULTILINGUAL_V1.corpus_version
    target = tmp_path / "corpus"
    shutil.copytree(source, target)
    documents = json.loads((target / "documents.json").read_text(encoding="utf-8"))
    documents["documents"][0]["text"] += " Altered."
    (target / "documents.json").write_text(json.dumps(documents, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(LegacyAdapterError, match="corpus fingerprint"):
        adapt_legacy_corpus(COMPACT_MULTILINGUAL_V1, target)


def test_adapter_rejects_tampered_manifest_counts(tmp_path):
    source = REPOSITORY_ROOT / "evaluation" / "corpora" / CROSS_LANGUAGE_MIRROR_V1.corpus_version
    target = tmp_path / "corpus"
    shutil.copytree(source, target)
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    manifest["document_count"] = 41
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LegacyAdapterError, match="manifest counts"):
        adapt_legacy_corpus(CROSS_LANGUAGE_MIRROR_V1, target)


def test_historical_confusable_cannot_also_be_a_required_source():
    dataset, _ = adapt_legacy_corpus(CROSS_LANGUAGE_MIRROR_V1)
    payload = dataset.model_dump(mode="json")
    first = payload["queries"][0]
    expected = first["required_groups"][0]["members"][0]
    first["historical_relationships"][0]["document_id"] = expected
    with pytest.raises(DatasetValidationError, match="cannot also be a historical confusable"):
        validate_dataset_v2(payload)


def test_adapted_historical_confusables_cannot_be_turned_into_judgments_by_the_adapter_basis():
    dataset, _ = adapt_legacy_corpus(COMPACT_MULTILINGUAL_V1)
    payload = dataset.model_dump(mode="json")
    query = next(item for item in payload["queries"] if item["historical_relationships"])
    query["judgments"].append(
        {"document_id": query["historical_relationships"][0]["document_id"], "grade": 0, "basis": "legacy_expected_source"}
    )
    with pytest.raises(DatasetValidationError, match="legacy_expected_source"):
        validate_dataset_v2(payload)
