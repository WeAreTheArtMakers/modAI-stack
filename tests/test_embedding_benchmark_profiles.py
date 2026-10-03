import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from app.core.config import Settings
from app.tools import benchmark_embedding_profile
from app.services.evaluation.embedding_profiles import (
    E5_MODEL_ID,
    E5_REVISION,
    E5_BASE_MODEL_ID,
    E5_BASE_REVISION,
    MINILM_BASELINE,
    MULTILINGUAL_E5_SMALL,
    MULTILINGUAL_E5_BASE,
    EmbeddingSpaceGuard,
    EmbeddingSpaceMismatchError,
    assert_same_embedding_space,
    validate_vector,
    validate_vectors,
)


def test_minilm_uses_identity_query_and_passage_preprocessing():
    assert MINILM_BASELINE.preprocess_query("policy question") == "policy question"
    assert MINILM_BASELINE.preprocess_passage("policy text") == "policy text"


def test_e5_uses_documented_asymmetric_query_and_passage_prefixes():
    assert MULTILINGUAL_E5_SMALL.preprocess_query("izin politikası nedir?") == (
        "query: izin politikası nedir?"
    )
    assert MULTILINGUAL_E5_SMALL.preprocess_passage("Employees receive 20 days.") == (
        "passage: Employees receive 20 days."
    )
    assert MINILM_BASELINE.preprocess_query("What is the policy?") == "What is the policy?"


def test_embedding_dimension_is_validated_even_when_models_share_384_dimensions():
    validate_vector([0.0] * 384, MINILM_BASELINE)
    validate_vector([0.0] * 384, MULTILINGUAL_E5_SMALL)
    with pytest.raises(EmbeddingSpaceMismatchError, match="expected 384, got 3"):
        validate_vectors([[0.0, 0.0, 0.0]], MULTILINGUAL_E5_SMALL)


def test_equal_dimensions_do_not_allow_mixing_different_model_spaces():
    assert MINILM_BASELINE.dimensions == MULTILINGUAL_E5_SMALL.dimensions
    assert MINILM_BASELINE.collection_name != MULTILINGUAL_E5_SMALL.collection_name
    with pytest.raises(EmbeddingSpaceMismatchError, match="does not match"):
        assert_same_embedding_space(MINILM_BASELINE, MULTILINGUAL_E5_SMALL)

    index_guard = EmbeddingSpaceGuard(MINILM_BASELINE)
    with pytest.raises(EmbeddingSpaceMismatchError, match="does not match"):
        index_guard.validate_vector(MULTILINGUAL_E5_SMALL, [0.0] * 384)

    changed_revision = replace(MULTILINGUAL_E5_SMALL, revision="f" * 40)
    with pytest.raises(EmbeddingSpaceMismatchError, match="does not match"):
        assert_same_embedding_space(MULTILINGUAL_E5_SMALL, changed_revision)


def test_profile_revision_and_safe_metadata_are_pinned_and_path_free():
    metadata = MULTILINGUAL_E5_SMALL.safe_metadata()
    assert metadata["model_id"] == E5_MODEL_ID
    assert metadata["revision"] == E5_REVISION
    assert metadata["license"] == "MIT"
    assert metadata["dimensions"] == 384
    assert metadata["max_input_tokens"] == 512
    assert metadata["query_prefix"] == "query: "
    assert metadata["passage_prefix"] == "passage: "
    assert not {"model_path", "cache_dir", "cache_path"}.intersection(metadata)
    assert "/private/tmp" not in str(metadata)


def test_e5_base_profile_metadata_preprocessing_and_vector_isolation():
    profile = MULTILINGUAL_E5_BASE
    metadata = profile.safe_metadata()
    assert (profile.model_id, profile.revision, profile.license) == (
        E5_BASE_MODEL_ID, E5_BASE_REVISION, "MIT"
    )
    assert (profile.dimensions, profile.max_input_tokens) == (768, 512)
    assert profile.preprocess_query("İzin nedir?") == "query: İzin nedir?"
    assert profile.preprocess_passage("Annual leave") == "passage: Annual leave"
    assert metadata["vector_space_identity"] == profile.vector_space_identity
    assert not {"model_path", "cache_dir", "cache_path"}.intersection(metadata)
    assert len({p.collection_name for p in (MINILM_BASELINE, MULTILINGUAL_E5_SMALL, profile)}) == 3
    validate_vector([0.0] * 768, profile)
    with pytest.raises(EmbeddingSpaceMismatchError, match="expected 768"):
        validate_vector([0.0] * 384, profile)
    for other in (MINILM_BASELINE, MULTILINGUAL_E5_SMALL):
        with pytest.raises(EmbeddingSpaceMismatchError, match="does not match"):
            assert_same_embedding_space(profile, other)


def test_e5_base_snapshot_requires_complete_artifacts_size_and_sha256(tmp_path, monkeypatch):
    profile = MULTILINGUAL_E5_BASE
    model_path = tmp_path / f"e5-base-{profile.revision}"
    for filename in benchmark_embedding_profile.E5_REQUIRED_SNAPSHOT_FILES:
        artifact = model_path / filename
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"test-only snapshot artifact")
    weights = model_path / "model.safetensors"
    monkeypatch.setattr(benchmark_embedding_profile, "E5_BASE_MODEL_SAFETENSORS_SIZE", weights.stat().st_size)
    expected = hashlib.sha256(weights.read_bytes()).hexdigest()
    monkeypatch.setattr(benchmark_embedding_profile, "E5_BASE_MODEL_SAFETENSORS_SHA256", expected)
    assert benchmark_embedding_profile._validate_local_model_snapshot(profile, model_path) == expected
    (model_path / "tokenizer.json").unlink()
    with pytest.raises(ValueError, match="tokenizer.json"):
        benchmark_embedding_profile._validate_local_model_snapshot(profile, model_path)
    (model_path / "tokenizer.json").write_bytes(b"test-only snapshot artifact")
    monkeypatch.setattr(benchmark_embedding_profile, "E5_BASE_MODEL_SAFETENSORS_SIZE", 1)
    with pytest.raises(ValueError, match="size"):
        benchmark_embedding_profile._validate_local_model_snapshot(profile, model_path)
    monkeypatch.setattr(benchmark_embedding_profile, "E5_BASE_MODEL_SAFETENSORS_SIZE", weights.stat().st_size)
    monkeypatch.setattr(benchmark_embedding_profile, "E5_BASE_MODEL_SAFETENSORS_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="SHA-256"):
        benchmark_embedding_profile._validate_local_model_snapshot(profile, model_path)


def test_experiment_profiles_do_not_change_production_embedding_or_top_k_defaults():
    settings = Settings(_env_file=None)
    assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.rag_top_k == 3


def test_incomplete_or_zero_byte_snapshot_weights_are_rejected_before_loading(tmp_path):
    model_path = tmp_path / MINILM_BASELINE.revision
    model_path.mkdir()
    (model_path / "model.safetensors").write_bytes(b"")

    with pytest.raises(ValueError, match="missing or empty"):
        benchmark_embedding_profile._run(
            MINILM_BASELINE,
            model_path,
            tmp_path / "does-not-need-to-be-read.json",
            tmp_path / "also-not-read.json",
        )


def _complete_e5_snapshot(tmp_path: Path) -> Path:
    model_path = tmp_path / f"e5-small-{MULTILINGUAL_E5_SMALL.revision}"
    for filename in benchmark_embedding_profile.E5_REQUIRED_SNAPSHOT_FILES:
        artifact = model_path / filename
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_bytes(b"test-only snapshot artifact")
    return model_path


def test_e5_snapshot_validation_requires_every_nonempty_pinned_artifact(tmp_path):
    model_path = _complete_e5_snapshot(tmp_path)
    (model_path / "tokenizer.json").unlink()

    with pytest.raises(ValueError, match="tokenizer.json"):
        benchmark_embedding_profile._validate_local_model_snapshot(
            MULTILINGUAL_E5_SMALL, model_path
        )


def test_e5_snapshot_validation_verifies_safetensors_sha256(tmp_path, monkeypatch):
    model_path = _complete_e5_snapshot(tmp_path)
    weights = model_path / "model.safetensors"
    weights.write_bytes(b"synthetic safetensors test fixture")
    expected = hashlib.sha256(weights.read_bytes()).hexdigest()
    monkeypatch.setattr(
        benchmark_embedding_profile,
        "E5_MODEL_SAFETENSORS_SHA256",
        expected,
    )

    assert benchmark_embedding_profile._validate_local_model_snapshot(
        MULTILINGUAL_E5_SMALL, model_path
    ) == expected

    monkeypatch.setattr(
        benchmark_embedding_profile,
        "E5_MODEL_SAFETENSORS_SHA256",
        "0" * 64,
    )
    with pytest.raises(ValueError, match="SHA-256"):
        benchmark_embedding_profile._validate_local_model_snapshot(
            MULTILINGUAL_E5_SMALL, model_path
        )


def test_snapshot_validator_rejects_a_non_pinned_revision_directory(tmp_path):
    model_path = tmp_path / ("f" * 40)
    model_path.mkdir()

    with pytest.raises(ValueError, match="exact pinned local snapshot directory name"):
        benchmark_embedding_profile._validate_local_model_snapshot(
            MULTILINGUAL_E5_SMALL, model_path
        )


def test_device_detection_reports_mps_availability_accurately(monkeypatch):
    from types import SimpleNamespace
    import sys

    fake_torch = SimpleNamespace(
        backends=SimpleNamespace(
            mps=SimpleNamespace(is_built=lambda: True, is_available=lambda: False)
        )
    )
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    assert benchmark_embedding_profile._resolve_device() == (
        "cpu",
        "MPS is built but unavailable in this runtime; CPU selected.",
    )


def test_runner_rejects_e5_profile_without_query_and_passage_prefixes():
    invalid_profile = replace(
        MULTILINGUAL_E5_SMALL,
        query_prefix="",
        passage_prefix="",
    )
    with pytest.raises(ValueError, match="require the documented query and passage prefixes"):
        benchmark_embedding_profile._run(
            invalid_profile,
            Path("missing-pinned-snapshot"),
            Path("dataset.json"),
            Path("documents.json"),
        )
