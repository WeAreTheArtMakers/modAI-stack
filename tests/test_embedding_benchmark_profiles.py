import pytest

from app.core.config import Settings
from app.services.evaluation.embedding_profiles import (
    E5_MODEL_ID,
    E5_REVISION,
    MINILM_BASELINE,
    MULTILINGUAL_E5_SMALL,
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


def test_experiment_profiles_do_not_change_production_embedding_or_top_k_defaults():
    settings = Settings(_env_file=None)
    assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.rag_top_k == 3
