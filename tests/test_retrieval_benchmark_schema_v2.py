import copy
import hashlib
import json
import subprocess
import sys
import unicodedata
from pathlib import Path

import pytest

from benchmarks.retrieval import validate as validate_cli
from benchmarks.retrieval.run import main as benchmark_main
from benchmarks.retrieval.runner import DeterministicFixtureEmbedder, RunConfiguration, run_benchmark_sync
from benchmarks.retrieval.schema import (
    BenchmarkDataset,
    BenchmarkDatasetV2,
    DatasetValidationError,
    assess_dataset,
    corpus_fingerprint_v2,
    dataset_fingerprint,
    dataset_fingerprints_v2,
    derived_direction,
    load_any_dataset,
    load_dataset,
    load_dataset_v2,
    validate_dataset_v2,
)


V1_FIXTURE = Path("benchmarks/retrieval/datasets/v1/fixture.json")
V2_EXAMPLE = Path("benchmarks/retrieval/datasets/v2/example.json")
V1_FIXTURE_SHA256 = "1a0001149f5ff8aea35e48a94eb9de3dce4bbb23286b6cd22654c1d109c79c84"
# Floats are rounded to 12 decimals before hashing: Qdrant's local scoring uses
# numpy kernels whose SIMD dispatch differs by CPU (observed: 1-ULP top_score
# differences between arm64, x86-64 AVX2 and the CI runner). The closest value
# sits 5e-14 from a rounding boundary, so the hash is stable yet still detects
# any score change above 1e-12; ordering, IDs and metrics are compared exactly.
V1_DRY_RUN_REPORT_SHA256 = "6ae1cac3b5a99e6effc97447caf382d45f11dee98ac5af39abef480c3734b641"
EXAMPLE_FINGERPRINTS = {
    "corpus_sha256": "001900bac066a490b0cf2d40aff7efec1175d051e4d8e933a5f322a3993269ad",
    "document_metadata_sha256": "815bfab653f43bd0d69b405f876ece8fccde8c47bc784a1586f90d43e87fce2f",
    "queries_sha256": "601b38ed311fa871ba697ad8177e53f3f0fbd411d63d6471e1e118292adcb180",
    "annotation_sha256": "4f1db9be7d18237aee49cae41c96f8995e955404a59295ebb8f29cb6d7de4395",
    "review_sha256": "d430e7f516d3857a67d6921846c9849df2a05482d41500fc33bfe2c250241a3e",
    "dataset_sha256": "78e60f53d4d5630214b82749bb563cdb4dc52f5cc348f125a8b7bafa78b482ae",
}
REVIEWERS = ["r-0000000a", "r-0000000b"]
GUIDE = {"version": "1.1", "sha256": "a" * 64}
TIMING_KEYS = {"median_embedding_latency_ms", "median_retrieval_latency_ms", "embedding_latency_ms", "retrieval_latency_ms"}


def example() -> dict:
    return json.loads(V2_EXAMPLE.read_text(encoding="utf-8"))


def document(payload, document_id):
    return next(item for item in payload["documents"] if item["document_id"] == document_id)


def query(payload, query_id):
    return next(item for item in payload["queries"] if item["query_id"] == query_id)


def judgment(payload, query_id, document_id):
    return next(item for item in query(payload, query_id)["judgments"] if item["document_id"] == document_id)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def real_lane() -> dict:
    payload = example()
    payload["lane"] = "real_representative"
    payload["labeling_guide"] = GUIDE
    for item in payload["documents"]:
        item["provenance"] = {
            "source_class": "public_real",
            "source_ref": f"https://example.invalid/policies/{item['document_id']}",
            "license": "CC-BY-4.0",
            "access_policy": "public",
            "original_sha256": "b" * 64,
            "extraction": {
                "extractor": "app.services.documents.parser.extract_text",
                "extractor_source_sha": "c" * 40,
                "raw_text_sha256": sha(item["text"]),
                "text_transform": "none",
            },
            "pii_review": "not_required",
        }
    for item in payload["queries"]:
        item["review"] = {
            "status": "double_reviewed_agreed",
            "guide_version": "1.1",
            "reviewer_ids": REVIEWERS,
            "confidence": "high",
            "reviewed_on": "2026-10-01",
        }
        for entry in item["judgments"]:
            entry["basis"] = "human_review"
    return payload


def assert_invalid(payload, match: str):
    with pytest.raises(DatasetValidationError, match=match) as raised:
        validate_dataset_v2(payload)
    message = str(raised.value)
    for item in example()["documents"]:
        assert item["text"][:30] not in message
    for item in example()["queries"]:
        assert item["question"][:30] not in message
    return message


# ---------------------------------------------------------------- compatibility


def test_v1_fixture_loads_unchanged_with_pinned_fingerprint():
    dataset = load_dataset(V1_FIXTURE)
    assert isinstance(dataset, BenchmarkDataset)
    assert dataset_fingerprint(dataset) == V1_FIXTURE_SHA256
    assert dataset_fingerprint(load_any_dataset(V1_FIXTURE)) == V1_FIXTURE_SHA256


def test_v1_dry_run_report_is_unchanged():
    report = run_benchmark_sync(
        RunConfiguration(
            dataset=load_dataset(V1_FIXTURE),
            embedding_model="deterministic-hash-stub",
            embedding_revision="not-applicable",
            embedding_dimension=DeterministicFixtureEmbedder.dimension,
            query_prefix="",
            passage_prefix="",
            chunk_size=700,
            chunk_overlap=100,
            top_k=5,
            execution_mode="dry-run; synthetic hash vectors; not embedding-model quality",
            device="deterministic-stub",
            source_sha=None,
            source_sha_origin="unavailable",
        ),
        DeterministicFixtureEmbedder(),
    )

    def strip(value):
        if isinstance(value, dict):
            return {key: strip(item) for key, item in value.items() if key not in TIMING_KEYS}
        if isinstance(value, list):
            return [strip(item) for item in value]
        if isinstance(value, float):
            return round(value, 12)
        return value

    payload = {
        "schema_version": report["schema_version"],
        "metrics": strip(report["metrics"]),
        "cases": strip(report["cases"]),
        "metadata_keys": sorted(report["metadata"]),
    }
    assert report["schema_version"] == 2
    assert hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest() == V1_DRY_RUN_REPORT_SHA256


def test_v1_loader_and_runner_refuse_v2_without_echoing_content(capsys):
    with pytest.raises(ValueError, match="schema v2 is not supported") as raised:
        load_dataset(V2_EXAMPLE)
    assert "harcırahı" not in str(raised.value)
    with pytest.raises(SystemExit):
        benchmark_main(["--dry-run", "--dataset", str(V2_EXAMPLE), "--output", "/nonexistent-output"])
    captured = capsys.readouterr()
    assert "schema v2 is not supported" in captured.err
    assert "harcırahı" not in captured.err and "Visitor parking" not in captured.err
    with pytest.raises(TypeError, match="only accepts schema v1"):
        RunConfiguration(
            dataset=load_dataset_v2(V2_EXAMPLE),
            embedding_model="x",
            embedding_revision="x",
            embedding_dimension=1,
            query_prefix="",
            passage_prefix="",
            chunk_size=700,
            chunk_overlap=100,
            top_k=5,
            execution_mode="x",
            device="x",
            source_sha=None,
            source_sha_origin="unavailable",
        )


@pytest.mark.parametrize("version", [None, 3, True, "2"])
def test_version_dispatch_rejects_unknown_versions(tmp_path, version):
    payload = example()
    if version is None:
        payload.pop("schema_version")
    else:
        payload["schema_version"] = version
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(DatasetValidationError, match="schema_version"):
        load_any_dataset(path)


def test_version_dispatch_returns_typed_models():
    assert isinstance(load_any_dataset(V1_FIXTURE), BenchmarkDataset)
    assert isinstance(load_any_dataset(V2_EXAMPLE), BenchmarkDatasetV2)
    with pytest.raises(DatasetValidationError, match="schema_version must be 2"):
        load_dataset_v2(V1_FIXTURE)


# ---------------------------------------------------------------- example and semantics


def test_example_fixture_is_valid_with_pinned_fingerprints():
    dataset = load_dataset_v2(V2_EXAMPLE)
    assert dataset.lane == "fixture"
    assert dataset_fingerprints_v2(dataset).__dict__ == EXAMPLE_FINGERPRINTS


def test_example_directions_and_assessment_never_establish_quality():
    dataset = load_dataset_v2(V2_EXAMPLE)
    documents = {item.document_id: item for item in dataset.documents}
    assert [derived_direction(item, documents) for item in dataset.queries] == [
        "same_language",
        "same_language",
        "tr_to_en",
        "same_language",
        "same_language",
        "not_applicable",
    ]
    assessment = assess_dataset(dataset)
    assert assessment.judgment_grade_counts == {0: 2, 1: 3, 2: 8}
    assert assessment.unjudged_pair_count == 8 * 6 - 13
    assert not assessment.eligible_for_locking
    assert assessment.real_world_benchmark_status == "NOT YET ESTABLISHED"


def test_required_groups_encode_or_within_and_and_across_groups():
    dataset = load_dataset_v2(V2_EXAMPLE)
    overrun = next(item for item in dataset.queries if item.query_id == "q-en-meal-overrun")
    assert [(group.group_id, sorted(group.members)) for group in overrun.required_groups] == [
        ("a", ["travel-policy-2025-en", "travel-policy-2025-tr"]),
        ("b", ["expense-approval-en"]),
    ]
    grades = {item.document_id: item.grade for item in overrun.judgments}
    assert grades["finance-portal-guide-en"] == 1
    assert "finance-portal-guide-en" not in {member for group in overrun.required_groups for member in group.members}


def test_unjudged_documents_are_not_judged_irrelevant():
    dataset = load_dataset_v2(V2_EXAMPLE)
    expense = next(item for item in dataset.queries if item.query_id == "q-en-expense-approver")
    judged = {item.document_id: item.grade for item in expense.judgments}
    assert judged == {"expense-approval-en": 2, "parking-rules-en": 0}
    assert "onboarding-guide-en" not in judged


def test_turkish_offsets_are_code_points_not_utf8_bytes():
    payload = example()
    text = document(payload, "travel-policy-2025-tr")["text"]
    span = judgment(payload, "q-tr-meal-allowance", "travel-policy-2025-tr")["evidence"][0]
    assert sha(text[span["start"]:span["end"]]) == span["sha256"]
    byte_start = len(text[: span["start"]].encode("utf-8"))
    byte_end = len(text[: span["end"]].encode("utf-8"))
    assert (byte_start, byte_end) != (span["start"], span["end"])
    span["start"], span["end"] = byte_start, byte_end
    assert_invalid(payload, "digest does not match|exceeds the document length")


# ---------------------------------------------------------------- invalid structures


def _mutate(path_function):
    payload = example()
    path_function(payload)
    return payload


INVALID_CASES = [
    ("duplicate document", lambda p: p["documents"].append(copy.deepcopy(p["documents"][0])), "document IDs"),
    ("duplicate query", lambda p: p["queries"].append(copy.deepcopy(p["queries"][0])), "query IDs"),
    ("unknown member", lambda p: query(p, "q-en-expense-approver")["required_groups"][0]["members"].append("missing-doc")
     or query(p, "q-en-expense-approver")["judgments"].append(
         {"document_id": "missing-doc", "grade": 2, "basis": "fixture_authored", "evidence": []}), "unknown document"),
    ("invalid language", lambda p: p["documents"][0].update(language="de"), "language"),
    ("authoritative lane", lambda p: p.update(lane="authoritative"), "lane"),
    ("grade 3", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(grade=3), "grade"),
    ("uppercase scenario", lambda p: query(p, "q-en-expense-approver").update(scenario_id="Expense"), "scenario_id"),
    ("answerable without groups", lambda p: query(p, "q-en-expense-approver").update(required_groups=[]), "required groups"),
    ("unanswerable with groups", lambda p: query(p, "q-en-international-allowance").update(
        required_groups=[{"group_id": "a", "members": ["travel-policy-2025-en"]}]), "required groups"),
    ("empty group", lambda p: query(p, "q-en-expense-approver")["required_groups"][0].update(members=[]), "members"),
    ("duplicate member", lambda p: query(p, "q-en-expense-approver")["required_groups"][0]["members"].append(
        "expense-approval-en"), "duplicates"),
    ("duplicate group id", lambda p: query(p, "q-en-meal-overrun")["required_groups"][1].update(group_id="a"), "group IDs"),
    ("member graded supporting", lambda p: judgment(p, "q-en-expense-approver", "expense-approval-en").update(
        grade=1, evidence=[]), "needs a grade 2 judgment"),
    ("grade 2 outside groups", lambda p: judgment(p, "q-en-meal-overrun", "finance-portal-guide-en").update(grade=2),
     "must belong to a required group|must support"),
    ("grade 0 with evidence", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(
        evidence=copy.deepcopy(judgment(p, "q-en-expense-approver", "expense-approval-en")["evidence"])), "grade 0"),
    ("flag on grade 1", lambda p: judgment(p, "q-en-meal-overrun", "finance-portal-guide-en").update(
        flags=["confusable"]), "flags require grade 0"),
    ("duplicate judgment", lambda p: query(p, "q-en-expense-approver")["judgments"].append(
        {"document_id": "parking-rules-en", "grade": 0, "basis": "fixture_authored"}), "judged documents"),
    ("multi document with one group", lambda p: (
        query(p, "q-en-meal-overrun")["required_groups"].pop(),
        judgment(p, "q-en-meal-overrun", "expense-approval-en").update(grade=1, evidence=[]),
    ), "multi_document"),
    ("cross lingual same language", lambda p: query(p, "q-tr-expense-approver-cross").update(language="en"), "cross_lingual"),
    ("historical relationship outside legacy", lambda p: query(p, "q-en-expense-approver")["historical_relationships"].append(
        {"document_id": "parking-rules-en", "relation": "confusable", "legacy_corpus_version": "legacy",
         "legacy_case_id": "case-1", "legacy_document_id": 1}), "historical relationships"),
    ("human review on unreviewed query", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(
        basis="human_review"), "human_review"),
    ("legacy basis without legacy source", lambda p: judgment(p, "q-en-expense-approver", "expense-approval-en").update(
        basis="legacy_expected_source"), "legacy_expected_source"),
    ("legacy basis with grade 0", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(
        basis="legacy_expected_source"), "legacy_expected_source"),
    ("legacy source on fixture", lambda p: p.update(legacy_source={
        "corpus_version": "legacy", "legacy_corpus_sha256": "a" * 64, "legacy_dataset_sha256": "b" * 64,
        "adapter_version": "1", "limitations": ["evidence_spans_unavailable"]}), "synthetic_stress"),
    ("question with trailing space", lambda p: query(p, "q-en-expense-approver").update(
        question=query(p, "q-en-expense-approver")["question"] + " "), "whitespace"),
    ("local source path", lambda p: p["documents"][0]["provenance"].update(source_ref="/Users/someone/policy.pdf"),
     "local filesystem path"),
    ("missing evidence for member", lambda p: judgment(p, "q-tr-incident-deadline", "incident-procedure-tr").update(
        evidence=[]), "no evidence span"),
    ("evidence claims wrong group", lambda p: judgment(p, "q-en-meal-overrun", "expense-approval-en")["evidence"][0].update(
        supports_group="a"), "must support one of its required groups"),
    ("supporting evidence claims group", lambda p: judgment(p, "q-en-meal-overrun", "finance-portal-guide-en")["evidence"][0].update(
        supports_group="a"), "supporting evidence"),
    ("span past end", lambda p: judgment(p, "q-tr-incident-deadline", "incident-procedure-tr")["evidence"][0].update(
        end=10_000), "exceeds the document length"),
    ("zero length span", lambda p: judgment(p, "q-tr-incident-deadline", "incident-procedure-tr")["evidence"][0].update(
        end=35), "end > start"),
    ("digest mismatch", lambda p: judgment(p, "q-tr-incident-deadline", "incident-procedure-tr")["evidence"][0].update(
        sha256="0" * 64), "digest does not match"),
    ("unjudged translation sibling", lambda p: query(p, "q-tr-meal-allowance")["required_groups"][0]["members"].remove(
        "travel-policy-2025-en") or query(p, "q-tr-meal-allowance")["judgments"].pop(1), "translation sibling"),
    ("obsolete flag on current document", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(
        flags=["obsolete_version"]), "obsolete_version"),
    ("obsolete flag in historical question", lambda p: query(p, "q-tr-meal-allowance").update(temporal_intent="historical"),
     "temporal_intent"),
    ("current question requiring superseded", lambda p: (
        query(p, "q-tr-incident-deadline")["required_groups"][0]["members"].append("travel-policy-2024-tr"),
        query(p, "q-tr-incident-deadline")["judgments"].append({
            "document_id": "travel-policy-2024-tr", "grade": 2, "basis": "fixture_authored",
            "evidence": [{"start": 0, "end": 8, "sha256": sha("Kurgusal"), "supports_group": "a"}]})),
     "superseded document"),
    ("wrong variant without variants", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(
        flags=["wrong_variant"]), "wrong_variant requires a different variant"),
    ("near duplicate without wrong variant", lambda p: query(p, "q-en-expense-approver")["tags"].append("near_duplicate"),
     "near_duplicate"),
    ("unsuperseded superseded document", lambda p: [item.update(supersedes=[]) for item in p["documents"]],
     "not superseded by any document"),
    ("cross-family supersedes", lambda p: document(p, "expense-approval-en")["supersedes"].append("travel-policy-2024-tr"),
     "superseded documents of its family"),
    ("supersedes current document", lambda p: document(p, "travel-policy-2025-tr")["supersedes"].append(
        "travel-policy-2025-en"), "superseded documents of its family"),
    ("superseded date order", lambda p: document(p, "travel-policy-2024-tr").update(effective_from="2026-01-01"),
     "take effect after"),
    ("two current documents per language", lambda p: p["documents"].append(
        dict(copy.deepcopy(document(p, "expense-approval-en")), document_id="expense-approval-en-copy")),
     "only one current document per variant and language"),
    ("translation group repeats language", lambda p: p["documents"].append(
        dict(copy.deepcopy(document(p, "travel-policy-2025-en")), document_id="travel-policy-2025-en-b", variant_key="b")),
     "translation group travel-policy-2025 repeats a language"),
    ("translation group version mismatch", lambda p: document(p, "travel-policy-2025-en").update(version_label="2025b"),
     "share family, status and version"),
    ("double review with one reviewer", lambda p: query(p, "q-en-expense-approver").update(review={
        "status": "double_reviewed_agreed", "guide_version": "1.1", "reviewer_ids": ["r-0000000a"],
        "confidence": "high", "reviewed_on": "2026-10-01"}), "requires 2 reviewer"),
    ("non-pseudonymous reviewer", lambda p: query(p, "q-en-expense-approver").update(review={
        "status": "single_reviewed", "guide_version": "1.1", "reviewer_ids": ["alice"],
        "confidence": "high", "reviewed_on": "2026-10-01"}), "reviewer_ids"),
    ("reviewed without guide", lambda p: query(p, "q-en-expense-approver").update(review={
        "status": "single_reviewed", "guide_version": "1.1", "reviewer_ids": ["r-0000000a"],
        "confidence": "high", "reviewed_on": "2026-10-01"}), "labeling guide"),
]


@pytest.mark.parametrize(("name", "mutation", "match"), INVALID_CASES, ids=[case[0] for case in INVALID_CASES])
def test_invalid_datasets_are_rejected_without_echoing_content(name, mutation, match):
    assert_invalid(_mutate(mutation), match)


# ---------------------------------------------------------------- text policy


@pytest.mark.parametrize(
    ("transform", "match"),
    [
        (lambda text: unicodedata.normalize("NFD", text), "NFC"),
        (lambda text: text.replace(". ", ".\r\n", 1), "disallowed control"),
        (lambda text: "﻿" + text, "disallowed control"),
        (lambda text: text + "\ud800", "disallowed control|unicode string"),
        (lambda text: text + "\x85", "disallowed control"),
        (lambda text: "   ", "blank"),
    ],
    ids=["nfd", "carriage-return", "bom", "lone-surrogate", "c1-control", "blank"],
)
def test_document_text_must_already_be_exact_nfc(transform, match):
    payload = example()
    target = document(payload, "travel-policy-2025-tr")
    target["text"] = transform(target["text"])
    assert_invalid(payload, match)


def test_turkish_dotted_capital_i_is_one_code_point_only_in_nfc():
    assert len(unicodedata.normalize("NFC", "İ")) == 1
    assert len(unicodedata.normalize("NFD", "İ")) == 2
    payload = example()
    target = document(payload, "parking-rules-en")
    target["text"] = unicodedata.normalize("NFD", "İzinli ziyaretçi otoparkı.")
    assert_invalid(payload, "NFC")


def test_spans_cannot_split_combining_sequences_or_be_blank():
    payload = example()
    target = document(payload, "parking-rules-en")
    target["text"] = "Visitor parking q̇ area.  Second sentence."
    split_end = target["text"].index("̇")
    international = query(payload, "q-en-international-allowance")
    international["judgments"].append({
        "document_id": "parking-rules-en", "grade": 1, "basis": "fixture_authored",
        "evidence": [{"start": 0, "end": split_end, "sha256": sha(target["text"][:split_end])}],
    })
    assert_invalid(payload, "combining character")
    blank_start = target["text"].index("  ")
    international["judgments"][-1]["evidence"] = [
        {"start": blank_start, "end": blank_start + 2, "sha256": sha("  ")}
    ]
    assert_invalid(payload, "only whitespace")


# ---------------------------------------------------------------- lanes


def test_real_lane_accepts_only_reviewed_real_documents_and_never_establishes_quality():
    payload = real_lane()
    dataset = validate_dataset_v2(payload)
    assert not assess_dataset(dataset).eligible_for_locking
    payload["representativeness"] = {
        "attested_by": "r-0000000c",
        "attested_on": "2026-10-02",
        "scope": "Fictional representativeness statement for schema tests",
        "corpus_sha256": corpus_fingerprint_v2(dataset.documents),
    }
    assessment = assess_dataset(validate_dataset_v2(payload))
    assert assessment.eligible_for_locking and assessment.representativeness_attested
    assert assessment.real_world_benchmark_status == "NOT YET ESTABLISHED"
    assert assessment.real_document_count == 8 and assessment.synthetic_document_count == 0


REAL_LANE_INVALID = [
    ("synthetic document", lambda p: p["documents"][0].update(provenance={
        "source_class": "synthetic_authored", "source_ref": "fixture", "access_policy": "public",
        "pii_review": "not_required"}), "must not contain synthetic documents"),
    ("no labeling guide", lambda p: p.update(labeling_guide=None), "labeling guide"),
    ("evidence unavailable", lambda p: [p.update(evidence_labels="unavailable")]
     + [entry.update(evidence=[]) for item in p["queries"] for entry in item["judgments"]], "character spans"),
    ("generator labels", lambda p: query(p, "q-en-international-allowance").update(
        review={"status": "generator_labeled"}, judgments=[]), "generator labels"),
    ("fixture basis", lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(basis="fixture_authored"),
     "fixture_authored"),
    ("license missing", lambda p: p["documents"][0]["provenance"].update(license=None), "license"),
    ("internal document public", lambda p: p["documents"][0]["provenance"].update(
        source_class="internal_approved", license=None,
        usage_authorization={"authorized_by": "r-0000000d", "authorization_ref": "DC-1", "authorized_on": "2026-09-01"},
        pii_review="completed"), "public access policy"),
    ("internal document without authorization", lambda p: p["documents"][0]["provenance"].update(
        source_class="internal_approved", access_policy="internal_restricted", pii_review="completed"),
     "usage authorization"),
    ("internal document without pii review", lambda p: p["documents"][0]["provenance"].update(
        source_class="internal_approved", access_policy="internal_restricted",
        usage_authorization={"authorized_by": "r-0000000d", "authorization_ref": "DC-1", "authorized_on": "2026-09-01"}),
     "PII review"),
    ("raw text hash mismatch", lambda p: p["documents"][0]["provenance"]["extraction"].update(raw_text_sha256="d" * 64),
     "raw_text_sha256"),
    ("attestation mismatch", lambda p: p.update(representativeness={
        "attested_by": "r-0000000c", "attested_on": "2026-10-02", "scope": "scope", "corpus_sha256": "e" * 64}),
     "does not match the current corpus"),
    ("guide version mismatch", lambda p: query(p, "q-en-expense-approver")["review"].update(guide_version="2.0"),
     "different labeling guide"),
    ("adjudicator is reviewer", lambda p: query(p, "q-en-expense-approver").update(review={
        "status": "double_reviewed_adjudicated", "guide_version": "1.1", "reviewer_ids": REVIEWERS,
        "adjudicator_id": REVIEWERS[0], "confidence": "high", "reviewed_on": "2026-10-01"}), "adjudicator"),
]


@pytest.mark.parametrize(("name", "mutation", "match"), REAL_LANE_INVALID, ids=[case[0] for case in REAL_LANE_INVALID])
def test_real_lane_constraints(name, mutation, match):
    payload = real_lane()
    mutation(payload)
    assert_invalid(payload, match)


def test_attestation_outside_real_lane_and_real_documents_in_fixture_are_rejected():
    payload = example()
    payload["representativeness"] = {
        "attested_by": "r-0000000c", "attested_on": "2026-10-02", "scope": "scope", "corpus_sha256": "e" * 64,
    }
    assert_invalid(payload, "real_representative lane")
    payload = example()
    payload["documents"][0]["provenance"] = real_lane()["documents"][0]["provenance"]
    assert_invalid(payload, "only contain synthetic documents")


# ---------------------------------------------------------------- fingerprints


def _fingerprints(payload) -> dict:
    return dataset_fingerprints_v2(validate_dataset_v2(payload)).__dict__


def test_fingerprints_ignore_list_order():
    payload = example()
    payload["documents"].reverse()
    payload["queries"].reverse()
    for item in payload["queries"]:
        item["judgments"].reverse()
        for group in item["required_groups"]:
            group["members"].reverse()
    assert _fingerprints(payload) == EXAMPLE_FINGERPRINTS


@pytest.mark.parametrize(
    ("mutation", "changed"),
    [
        (lambda p: document(p, "parking-rules-en").update(text="Visitor parking is limited."), {"corpus_sha256"}),
        (lambda p: document(p, "parking-rules-en").update(domain="general"), {"document_metadata_sha256"}),
        (lambda p: query(p, "q-en-international-allowance").update(
            question="What is the international meal allowance?"), {"queries_sha256"}),
        (lambda p: judgment(p, "q-en-expense-approver", "parking-rules-en").update(grade=1), {"annotation_sha256"}),
        (lambda p: query(p, "q-en-expense-approver")["judgments"].pop(), {"annotation_sha256"}),
    ],
    ids=["source-text", "document-metadata", "query-text", "label", "judged-to-unjudged"],
)
def test_fingerprint_change_matrix(mutation, changed):
    payload = example()
    mutation(payload)
    after = _fingerprints(payload)
    differing = {key for key, value in after.items() if value != EXAMPLE_FINGERPRINTS[key]}
    assert differing == changed | {"dataset_sha256"}


def test_review_change_only_moves_review_fingerprint():
    payload = real_lane()
    before = _fingerprints(payload)
    query(payload, "q-en-expense-approver")["review"]["confidence"] = "medium"
    after = _fingerprints(payload)
    assert {key for key in after if after[key] != before[key]} == {"review_sha256", "dataset_sha256"}


# ---------------------------------------------------------------- validation CLI


def test_validation_cli_reports_counts_and_fingerprints_without_content(capsys):
    assert validate_cli.main([str(V2_EXAMPLE)]) == 0
    output = capsys.readouterr().out
    summary = json.loads(output)
    assert summary["status"] == "VALID" and summary["lane"] == "fixture"
    assert summary["fingerprints"]["dataset_sha256"] == EXAMPLE_FINGERPRINTS["dataset_sha256"]
    assert summary["judgment_grade_counts"] == {"0": 2, "1": 3, "2": 8} and summary["unjudged_pair_count"] == 35
    assert summary["real_document_count"] == 0 and summary["synthetic_document_count"] == 8
    for item in example()["documents"]:
        assert item["text"][:20] not in output
    for item in example()["queries"]:
        assert item["question"][:20] not in output
    assert str(V2_EXAMPLE) not in output and "datasets/v2" not in output


def test_validation_cli_fails_closed_without_echoing_content(tmp_path, capsys):
    payload = example()
    judgment(payload, "q-tr-incident-deadline", "incident-procedure-tr")["evidence"][0]["sha256"] = "0" * 64
    path = tmp_path / "private-dataset.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert validate_cli.main([str(path)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "INVALID" in captured.err and "Şüpheli" not in captured.err and str(tmp_path) not in captured.err


def test_validation_cli_reports_v1_and_does_not_import_the_application(capsys):
    assert validate_cli.main([str(V1_FIXTURE)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["dataset_sha256"] == V1_FIXTURE_SHA256
    assert summary["graded_relevance"] == "not available in schema v1"
    probe = "import sys, benchmarks.retrieval.validate; assert not any(m == 'app' or m.startswith('app.') for m in sys.modules)"
    subprocess.run([sys.executable, "-c", probe], check=True)
