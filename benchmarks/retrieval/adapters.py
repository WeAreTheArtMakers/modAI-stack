"""Read-only adapters from legacy synthetic corpora to dataset schema v2.

Legacy relevance is mapped only where semantics are equivalent: the expected
source becomes a single-member required group. Confusable references are kept
as historical relationships and stay unjudged; no grade, evidence span or
translation equivalence is inferred.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from app.services.evaluation.models import EvaluationDataset, dataset_fingerprint
from app.services.evaluation.synthetic_corpus import corpus_fingerprint
from benchmarks.retrieval.schema import (
    BenchmarkDatasetV2,
    DatasetValidationError,
    derived_direction,
    validate_dataset_v2,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BASE_LIMITATIONS = (
    "document_families_unavailable",
    "evidence_spans_unavailable",
    "expected_facts_not_represented",
    "historical_confusables_unjudged",
    "knowledge_base_scope_not_represented",
    "legacy_category_not_represented",
    "retrieval_policy_not_represented",
)


class LegacyAdapterError(DatasetValidationError):
    """The legacy corpus does not match its pinned identity or invariants."""


@dataclass(frozen=True)
class LegacyCorpusSpec:
    corpus_version: str
    corpus_sha256: str
    dataset_sha256: str
    document_count: int
    case_count: int
    no_answer_count: int
    direction_counts: dict[str, int]
    confusable_reference_count: int
    limitations: tuple[str, ...]


COMPACT_MULTILINGUAL_V1 = LegacyCorpusSpec(
    corpus_version="compact-multilingual-v1",
    corpus_sha256="81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b",
    dataset_sha256="12fb1371a48a5b4b019f75e5bb423ebbfe2ac0d257d214c38581e6c8f540ee49",
    document_count=44,
    case_count=156,
    no_answer_count=24,
    direction_counts={"same_language": 88, "tr_to_en": 22, "en_to_tr": 22, "not_applicable": 24},
    confusable_reference_count=492,
    limitations=_BASE_LIMITATIONS,
)

# Mirror pairs are same-fact translations by construction, but legacy relevance
# is target-language only; the equivalent translation is not added to a group.
CROSS_LANGUAGE_MIRROR_V1 = LegacyCorpusSpec(
    corpus_version="cross-language-mirror-v1",
    corpus_sha256="95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833595e188c",
    dataset_sha256="2075b70cbcb9ec97b93a60e246c340946d7949869f514103fa9eff76ec26eb59",
    document_count=40,
    case_count=40,
    no_answer_count=0,
    direction_counts={"tr_to_en": 20, "en_to_tr": 20},
    confusable_reference_count=40,
    limitations=tuple(sorted((*_BASE_LIMITATIONS, "required_groups_may_be_incomplete"))),
)


@dataclass(frozen=True)
class AdapterReport:
    """Counts and identities only; never contains corpus text."""

    corpus_version: str
    legacy_corpus_sha256: str
    legacy_dataset_sha256: str
    document_count: int
    query_count: int
    answerable_query_count: int
    expected_source_relationships: int
    historical_confusable_relationships: int
    direction_counts: dict[str, int]
    limitations: tuple[str, ...]


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LegacyAdapterError(f"legacy corpus file {path.name} could not be read") from exc


def _document_id(legacy_id: int) -> str:
    return f"doc-{legacy_id:03d}"


def _primary_category(case, direction: str) -> str:
    if case.case_type == "no_answer":
        return "unanswerable"
    if direction in {"tr_to_en", "en_to_tr"}:
        return "cross_lingual"
    return "semantic_distractor" if case.case_type == "hard_negative" else "single_document_fact"


def adapt_legacy_corpus(
    spec: LegacyCorpusSpec,
    corpus_dir: Path | None = None,
) -> tuple[BenchmarkDatasetV2, AdapterReport]:
    """Verify a pinned legacy corpus and return an in-memory schema-v2 dataset."""
    directory = corpus_dir or REPOSITORY_ROOT / "evaluation" / "corpora" / spec.corpus_version
    raw_dataset = _read_json(directory / "dataset.json")
    raw_documents = _read_json(directory / "documents.json")
    manifest = _read_json(directory / "manifest.json")

    try:
        dataset = EvaluationDataset.model_validate(raw_dataset)
    except ValueError as exc:
        raise LegacyAdapterError(f"{spec.corpus_version} dataset failed legacy validation") from exc
    documents = raw_documents.get("documents") if isinstance(raw_documents, dict) else None
    if not isinstance(documents, list) or not isinstance(manifest, dict):
        raise LegacyAdapterError(f"{spec.corpus_version} documents or manifest are malformed")

    computed = corpus_fingerprint(spec.corpus_version, dataset, documents)
    if computed != spec.corpus_sha256 or manifest.get("fingerprint_sha256") != spec.corpus_sha256:
        raise LegacyAdapterError(f"{spec.corpus_version} corpus fingerprint does not match the pinned value")
    if dataset_fingerprint(dataset) != spec.dataset_sha256:
        raise LegacyAdapterError(f"{spec.corpus_version} dataset fingerprint does not match the pinned value")

    cases = dataset.cases
    counts = (len(documents), len(cases), sum(case.case_type == "no_answer" for case in cases))
    if counts != (spec.document_count, spec.case_count, spec.no_answer_count):
        raise LegacyAdapterError(f"{spec.corpus_version} document or case counts do not match the pinned values")
    if (manifest.get("document_count"), manifest.get("case_count")) != (spec.document_count, spec.case_count):
        raise LegacyAdapterError(f"{spec.corpus_version} manifest counts do not match the pinned values")
    for case in cases:
        if (
            case.top_k != 3
            or case.knowledge_base_ids != [1]
            or case.case_type == "authorization_negative"
            or len(case.expected_document_ids) > 1
            or case.scenario_id is None
        ):
            raise LegacyAdapterError(f"{spec.corpus_version} case {case.id} has semantics this adapter cannot map")

    v2_documents = [
        {
            "document_id": _document_id(document["document_id"]),
            "language": document["language"],
            "text": document["text"],
            "source_family_id": _document_id(document["document_id"]),
            "provenance": {
                "source_class": "synthetic_generated",
                "source_ref": f"{spec.corpus_version}:document:{document['document_id']}",
                "access_policy": "public",
                "pii_review": "not_required",
            },
        }
        for document in documents
    ]
    languages = {_document_id(document["document_id"]): document["language"] for document in documents}

    queries = []
    for case in cases:
        expected = [_document_id(identifier) for identifier in case.expected_document_ids]
        answerable = case.case_type != "no_answer"
        if answerable and not expected:
            raise LegacyAdapterError(f"{spec.corpus_version} case {case.id} has no expected source")
        if not answerable:
            direction = "not_applicable"
        elif languages[expected[0]] == case.language:
            direction = "same_language"
        else:
            direction = f"{case.language}_to_{languages[expected[0]]}"
        primary = _primary_category(case, direction)
        queries.append(
            {
                "query_id": case.id,
                "scenario_id": case.scenario_id,
                "language": case.language,
                "question": case.question,
                "primary_category": primary,
                "tags": ["single_document_fact"] if primary in {"cross_lingual", "semantic_distractor"} else [],
                "answerable": answerable,
                "required_groups": [{"group_id": "g1", "members": expected}] if answerable else [],
                "judgments": [
                    {"document_id": document_id, "grade": 2, "basis": "legacy_expected_source"}
                    for document_id in expected
                ],
                "historical_relationships": [
                    {
                        "document_id": _document_id(identifier),
                        "relation": "confusable",
                        "legacy_corpus_version": spec.corpus_version,
                        "legacy_case_id": case.id,
                        "legacy_document_id": identifier,
                    }
                    for identifier in case.confusable_document_ids
                ],
                "review": {"status": "generator_labeled"},
            }
        )

    adapted = validate_dataset_v2(
        {
            "schema_version": 2,
            "dataset_id": f"{spec.corpus_version}-adapted",
            "dataset_version": "1.0.0",
            "title": f"{spec.corpus_version} (synthetic stress, adapted from legacy schema)",
            "lane": "synthetic_stress",
            "evidence_labels": "unavailable",
            "legacy_source": {
                "corpus_version": spec.corpus_version,
                "legacy_corpus_sha256": spec.corpus_sha256,
                "legacy_dataset_sha256": spec.dataset_sha256,
                "adapter_version": "1",
                "limitations": list(spec.limitations),
            },
            "documents": v2_documents,
            "queries": queries,
        }
    )

    documents_by_id = {document.document_id: document for document in adapted.documents}
    directions = dict(Counter(derived_direction(query, documents_by_id) for query in adapted.queries))
    historical = sum(len(query.historical_relationships) for query in adapted.queries)
    if directions != spec.direction_counts or historical != spec.confusable_reference_count:
        raise LegacyAdapterError(f"{spec.corpus_version} adapted directions or relationships do not match")
    report = AdapterReport(
        corpus_version=spec.corpus_version,
        legacy_corpus_sha256=spec.corpus_sha256,
        legacy_dataset_sha256=spec.dataset_sha256,
        document_count=len(adapted.documents),
        query_count=len(adapted.queries),
        answerable_query_count=sum(query.answerable for query in adapted.queries),
        expected_source_relationships=sum(len(query.required_groups) for query in adapted.queries),
        historical_confusable_relationships=historical,
        direction_counts=directions,
        limitations=spec.limitations,
    )
    return adapted, report
