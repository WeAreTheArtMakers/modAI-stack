import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.retrieval.metrics import QueryOutcome, aggregate_metrics
from benchmarks.retrieval.reporting import serialize_json
from benchmarks.retrieval.runner import (
    DeterministicFixtureEmbedder,
    RunConfiguration,
    run_benchmark_sync,
)
from benchmarks.retrieval import runner as benchmark_runner
from benchmarks.retrieval.run import build_parser
from benchmarks.retrieval.run import main as benchmark_main, resolve_embedding_options
from benchmarks.retrieval.safety import (
    BenchmarkSafetyError,
    OwnedBenchmarkCollection,
    assert_endpoint_isolated,
    create_owned_collection,
    validate_collection_name,
)
from benchmarks.retrieval.schema import BenchmarkDataset, dataset_fingerprint, load_dataset
from app.services.evaluation.embedding_profiles import (
    MINILM_BASELINE,
    MULTILINGUAL_E5_SMALL,
)


FIXTURE = Path("benchmarks/retrieval/datasets/v1/fixture.json")


def test_fixture_corpus_has_required_languages_and_categories():
    dataset = load_dataset(FIXTURE)
    assert {case.language for case in dataset.queries} == {"tr", "en", "mixed"}
    categories = {category for case in dataset.queries for category in case.categories}
    assert categories == {
        "single_document_fact",
        "multi_document",
        "long_document",
        "semantic_distractors",
        "unanswerable",
    }


def test_duplicate_document_and_query_ids_are_rejected():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"].append(dict(raw["queries"][0]))
    with pytest.raises(ValueError, match="query IDs must be unique"):
        BenchmarkDataset.model_validate(raw)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["documents"].append(dict(raw["documents"][0]))
    with pytest.raises(ValueError, match="document IDs must be unique"):
        BenchmarkDataset.model_validate(raw)


def test_dataset_fingerprint_is_stable_and_tracks_semantic_changes():
    dataset = load_dataset(FIXTURE)
    changed = dataset.model_copy(
        update={
            "queries": [
                dataset.queries[0].model_copy(update={"question": "Different synthetic question"}),
                *dataset.queries[1:],
            ]
        }
    )
    assert dataset_fingerprint(dataset) == dataset_fingerprint(dataset)
    assert dataset_fingerprint(dataset) != dataset_fingerprint(changed)


def test_answerable_query_requires_expected_document():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"][0]["expected_document_ids"] = []
    with pytest.raises(ValueError, match="answerable queries require"):
        BenchmarkDataset.model_validate(raw)


def test_retrieval_categories_enforce_their_document_cardinality():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"][0]["categories"] = ["multi_document"]
    with pytest.raises(ValueError, match="at least two expected documents"):
        BenchmarkDataset.model_validate(raw)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"][0]["expected_document_ids"] = ["doc-annual-leave-tr", "doc-benefits-en"]
    with pytest.raises(ValueError, match="exactly one expected document"):
        BenchmarkDataset.model_validate(raw)


def test_unanswerable_query_must_not_label_relevant_documents():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"][-1]["expected_document_ids"] = ["doc-benefits-en"]
    with pytest.raises(ValueError, match="cannot declare relevant"):
        BenchmarkDataset.model_validate(raw)


def test_unknown_document_and_unstable_chunk_references_are_rejected():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"][0]["expected_document_ids"] = ["production-document-23"]
    with pytest.raises(ValueError, match="unknown document"):
        BenchmarkDataset.model_validate(raw)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["queries"][0]["expected_chunk_ids"] = ["doc-annual-leave-tr::chunk-x"]
    with pytest.raises(ValueError, match="stable document::chunk"):
        BenchmarkDataset.model_validate(raw)


def _outcome(
    query_id,
    *,
    expected,
    retrieved,
    answerable=True,
    language="en",
    categories=("single_document_fact",),
    chunks=(),
    retrieved_chunks=(),
    retrieved_chunk_documents=(),
    top_score=0.8,
):
    return QueryOutcome(
        query_id=query_id,
        language=language,
        categories=tuple(categories),
        answerable=answerable,
        expected_document_ids=tuple(expected),
        expected_chunk_ids=tuple(chunks),
        retrieved_document_ids=tuple(retrieved),
        retrieved_chunk_ids=tuple(retrieved_chunks),
        top_score=top_score,
        embedding_latency_ms=2.0,
        retrieval_latency_ms=1.0,
        retrieved_chunk_document_ids=tuple(retrieved_chunk_documents),
    )


def test_hand_calculated_recall_hit_mrr_and_source_precision_at_1_3_5():
    outcomes = [
        _outcome("q1", expected=("a", "b"), retrieved=("x", "a", "b", "y", "z")),
        _outcome("q2", expected=("c",), retrieved=("c", "x", "y", "z")),
    ]
    global_metrics = aggregate_metrics(outcomes)["global"]
    assert global_metrics["recall_at_k"] == {"1": 0.5, "3": 1.0, "5": 1.0}
    assert global_metrics["hit_at_k"] == {"1": 0.5, "3": 1.0, "5": 1.0}
    assert global_metrics["mrr_at_k"] == {"1": 0.5, "3": 0.75, "5": 0.75}
    assert global_metrics["source_precision_at_k"] == {
        "1": 0.5,
        "3": 0.5,
        "5": 0.333333,
    }


def test_no_relevant_results_score_zero_and_chunk_metrics_require_labels():
    outcomes = [
        _outcome("q1", expected=("a", "b"), retrieved=("x", "y"), chunks=("a::chunk-0000",), retrieved_chunks=("x::chunk-0000",)),
        _outcome("q2", expected=(), retrieved=("x",), answerable=False, categories=("unanswerable",)),
    ]
    summary = aggregate_metrics(outcomes)["global"]
    assert summary["recall_at_k"]["5"] == 0.0
    assert summary["hit_at_k"]["5"] == 0.0
    assert summary["mrr_at_k"]["5"] == 0.0
    assert summary["chunk_recall_at_k"]["5"] == 0.0
    assert summary["unanswerable_candidate_return_rate"] == 1.0
    assert "no_answer_detection_accuracy" not in summary


def test_multiple_relevant_documents_are_recalled_as_a_fraction():
    outcome = _outcome("q", expected=("a", "b", "c"), retrieved=("b", "x", "a"))
    metrics = aggregate_metrics([outcome])["global"]
    assert metrics["recall_at_k"]["1"] == pytest.approx(1 / 3)
    assert metrics["recall_at_k"]["3"] == pytest.approx(2 / 3)
    assert metrics["hit_at_k"]["1"] == 1.0


def test_document_cutoffs_deduplicate_repeated_sources_within_top_chunk_results():
    outcome = _outcome(
        "q",
        expected=("b",),
        retrieved=("a", "b", "c", "d"),
        retrieved_chunks=("a::chunk-0000", "a::chunk-0001", "b::chunk-0000", "c::chunk-0000", "d::chunk-0000"),
        retrieved_chunk_documents=("a", "a", "b", "c", "d"),
    )
    metrics = aggregate_metrics([outcome])["global"]
    assert metrics["recall_at_k"] == {"1": 0.0, "3": 1.0, "5": 1.0}
    assert metrics["hit_at_k"] == {"1": 0.0, "3": 1.0, "5": 1.0}
    assert metrics["mrr_at_k"]["3"] == 0.5
    assert metrics["source_precision_at_k"]["3"] == 0.5


def test_language_and_overlapping_category_aggregation_do_not_duplicate_global_cases():
    outcomes = [
        _outcome("tr", expected=("a",), retrieved=("a",), language="tr", categories=("single_document_fact", "semantic_distractors")),
        _outcome("mix", expected=("b",), retrieved=(), language="mixed", categories=("long_document",)),
    ]
    summary = aggregate_metrics(outcomes)
    assert summary["global"]["query_count"] == 2
    assert summary["by_language"]["tr"]["query_count"] == 1
    assert summary["by_language"]["mixed"]["query_count"] == 1
    assert summary["by_category"]["semantic_distractors"]["query_count"] == 1
    assert summary["by_category"]["long_document"]["query_count"] == 1


def test_collection_name_must_be_benchmark_scoped_and_not_production():
    with pytest.raises(BenchmarkSafetyError, match="benchmark collection name"):
        validate_collection_name("rag_documents")
    with pytest.raises(BenchmarkSafetyError):
        validate_collection_name("modai_space_0123456789abcdef")
    validate_collection_name("modai_benchmark_0123456789abcdef")


def test_configured_production_qdrant_endpoint_is_refused_without_echoing_url():
    production = "http://user:password@qdrant:6333"
    with pytest.raises(BenchmarkSafetyError) as error:
        assert_endpoint_isolated("http://qdrant:6333/", production)
    assert "password" not in str(error.value)
    assert_endpoint_isolated("http://127.0.0.1:16333", production)
    with pytest.raises(BenchmarkSafetyError, match="must not be the production endpoint"):
        benchmark_runner._make_client(
            benchmark_endpoint="http://qdrant:6333/",
            production_endpoint="http://qdrant:6333",
        )
    with pytest.raises(BenchmarkSafetyError, match="remote Qdrant endpoints are unsupported"):
        benchmark_runner._make_client(
            benchmark_endpoint="http://127.0.0.1:16333",
            production_endpoint="http://qdrant:6333",
        )


def test_cleanup_cannot_delete_a_collection_not_created_by_this_run():
    class Client:
        deleted = []

        def delete_collection(self, *, collection_name):
            self.deleted.append(collection_name)

    client = Client()
    lease = OwnedBenchmarkCollection(client, "modai_benchmark_0123456789abcdef", False)
    with pytest.raises(BenchmarkSafetyError, match="not created"):
        lease.delete()
    assert client.deleted == []


def test_cleanup_refuses_arbitrary_production_collection_even_if_lease_is_forged():
    class Client:
        deleted = []

        def delete_collection(self, *, collection_name):
            self.deleted.append(collection_name)

    client = Client()
    lease = OwnedBenchmarkCollection(client, "rag_documents", True)
    with pytest.raises(BenchmarkSafetyError):
        lease.delete()
    assert client.deleted == []


def test_existing_collection_is_not_reused_or_overwritten():
    class Client:
        def get_collections(self):
            return SimpleNamespace(collections=[SimpleNamespace(name="modai_benchmark_0123456789abcdef")])

        def create_collection(self, **kwargs):
            raise AssertionError("must not overwrite")

    with pytest.raises(BenchmarkSafetyError, match="refusing to reuse"):
        create_owned_collection(Client(), name="modai_benchmark_0123456789abcdef", dimensions=4)


def test_embedding_override_isolated_and_pinned_profiles_apply_preprocessing():
    baseline = resolve_embedding_options(MINILM_BASELINE.model_id)
    e5 = resolve_embedding_options(MULTILINGUAL_E5_SMALL.model_id)
    assert baseline == (MINILM_BASELINE.model_id, MINILM_BASELINE.revision, "", "")
    assert e5 == (
        MULTILINGUAL_E5_SMALL.model_id,
        MULTILINGUAL_E5_SMALL.revision,
        "query: ",
        "passage: ",
    )
    with pytest.raises(ValueError, match="pinned --revision"):
        resolve_embedding_options("org/other-local-model")


def test_embedding_selection_does_not_mutate_production_setting():
    from app.core.config import get_settings

    before = get_settings().embedding_model
    resolve_embedding_options(MULTILINGUAL_E5_SMALL.model_id)
    assert get_settings().embedding_model == before


def test_benchmark_client_is_always_in_memory_even_if_production_url_is_configured(monkeypatch):
    calls = []

    class FakeQdrantClient:
        def __init__(self, *args, **kwargs):
            calls.append((args, kwargs))

    monkeypatch.setattr(benchmark_runner, "QdrantClient", FakeQdrantClient)
    monkeypatch.setenv("QDRANT_URL", "http://qdrant:6333")
    benchmark_runner._make_client()
    assert calls == [((':memory:',), {})]
    assert all("--qdrant-url" not in action.option_strings for action in build_parser()._actions)


def test_fixture_dry_run_uses_in_memory_qdrant_and_safe_aggregate_report(monkeypatch):
    dataset = load_dataset(FIXTURE)
    config = RunConfiguration(
        dataset=dataset,
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
        git_sha="test-sha",
    )
    report = run_benchmark_sync(config, DeterministicFixtureEmbedder())
    serialized = serialize_json(report)
    assert report["metadata"]["qdrant_isolation_mode"].startswith("local in-memory")
    assert report["classification"] == "Fixture / engineering validation baseline"
    assert report["real_world_benchmark_status"] == "NOT YET ESTABLISHED"
    assert report["metadata"]["chunk_count"] > len(dataset.documents)
    assert "Poyraz Teknoloji çalışanları" not in serialized
    assert "retry window is 48 seconds" not in serialized
    assert report["metrics"]["global"]["unanswerable_query_count"] == 2


def test_authoritative_corpus_dry_run_does_not_establish_real_world_quality():
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["classification"] = "authoritative"
    dataset = BenchmarkDataset.model_validate(raw)
    report = run_benchmark_sync(
        RunConfiguration(
            dataset=dataset,
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
            git_sha="test-sha",
        ),
        DeterministicFixtureEmbedder(),
    )
    assert report["real_world_benchmark_status"] == "NOT YET ESTABLISHED"


def test_cli_dry_run_writes_both_report_formats_without_model_download(tmp_path):
    exit_code = benchmark_main(
        [
            "--dry-run",
            "--dataset",
            str(FIXTURE),
            "--chunk-size",
            "700",
            "--chunk-overlap",
            "100",
            "--output",
            str(tmp_path),
        ]
    )
    assert exit_code == 0
    assert (tmp_path / "retrieval-benchmark-v1.json").is_file()
    assert (tmp_path / "retrieval-benchmark-v1.md").is_file()
    markdown = (tmp_path / "retrieval-benchmark-v1.md").read_text(encoding="utf-8")
    assert "hash-stub vectors" in markdown


def test_authoritative_corpus_requires_explicit_human_review_confirmation(tmp_path):
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["classification"] = "authoritative"
    private_dataset = tmp_path / "private-evaluation.json"
    private_dataset.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SystemExit):
        benchmark_main(["--dry-run", "--dataset", str(private_dataset), "--output", str(tmp_path / "out")])


def test_json_serialization_is_stable_for_same_report():
    report = {"z": 1, "a": {"second": 2, "first": 1}}
    assert serialize_json(report) == serialize_json(report)
    assert serialize_json(report).index('"a"') < serialize_json(report).index('"z"')


def test_import_does_not_register_routes_connect_database_or_import_alembic():
    source = (
        "import sys; import benchmarks.retrieval.run; import benchmarks.retrieval.runner; "
        "assert 'app.api.routes.rag' not in sys.modules; "
        "assert 'alembic' not in sys.modules; "
        "assert 'app.db.session' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", source], check=True, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
