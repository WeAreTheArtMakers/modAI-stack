from dataclasses import replace
from uuid import UUID

import pytest

from app.core.config import Settings
from app.services.qdrant import QdrantService
from app.services.rag.retrieval_contracts import (
    AuthorizedTenantGeneration,
    EmbeddingSpaceContract,
    GenerationWriteScope,
    LegacyUnverifiedRetrieval,
    MaterializationContract,
    ResolvedRetrievalIndex,
    RetrievalCompatibilityError,
    RetrievalContractError,
    RetrievalScopeError,
    collection_name_for_space,
    require_generation_match,
    require_materialization_match,
    require_space_match,
    validate_vector,
)


def minilm_space() -> EmbeddingSpaceContract:
    return EmbeddingSpaceContract(
        schema_version=1,
        model_id="sentence-transformers/all-MiniLM-L6-v2",
        model_revision="test-pinned-revision",
        dimensions=384,
        max_input_tokens=256,
        query_preprocessing="identity-v1",
        passage_preprocessing="identity-v1",
        tokenizer_identity="minilm-tokenizer-v1",
        normalize_embeddings=True,
        distance_metric="cosine",
    )


def bge_space(*, dimensions: int = 1024) -> EmbeddingSpaceContract:
    return EmbeddingSpaceContract(
        schema_version=1,
        model_id="BAAI/bge-m3",
        model_revision="31e47391fcbda65be526abe98e646b3c6cd845a8",
        dimensions=dimensions,
        max_input_tokens=8192,
        query_preprocessing="identity-v1",
        passage_preprocessing="identity-v1",
        tokenizer_identity="bge-m3-tokenizer-v1",
        normalize_embeddings=True,
        distance_metric="cosine",
    )


def materialization() -> MaterializationContract:
    return MaterializationContract(
        schema_version=1,
        chunker_id="modai-chunker-v1",
        chunk_size=700,
        chunk_overlap=100,
        payload_schema_version="rag-payload-v1",
    )


def test_space_hash_is_deterministic_and_contract_only():
    first = minilm_space()
    second = minilm_space()

    assert first.space_sha256 == second.space_sha256
    assert len(first.space_sha256) == 64
    assert "display_name" not in first.canonical_payload()
    assert "profile_id" not in first.canonical_payload()


def test_space_hash_changes_for_compatibility_fields():
    base = minilm_space()

    assert replace(
        base,
        model_revision="another-revision",
    ).space_sha256 != base.space_sha256

    assert replace(
        base,
        dimensions=768,
    ).space_sha256 != base.space_sha256

    assert replace(
        base,
        query_preprocessing="query-prefix-v1",
    ).space_sha256 != base.space_sha256


def test_equal_dimension_different_models_are_different_spaces():
    mini = minilm_space()
    bge_same_dimension = bge_space(dimensions=384)

    assert mini.dimensions == bge_same_dimension.dimensions
    assert mini.space_sha256 != bge_same_dimension.space_sha256


def test_materialization_identity_is_separate_from_embedding_space():
    space = minilm_space()
    base = materialization()
    changed_chunking = replace(base, chunk_size=800)
    changed_payload = replace(
        base,
        payload_schema_version="rag-payload-v2",
    )

    assert changed_chunking.materialization_sha256 != base.materialization_sha256
    assert changed_payload.materialization_sha256 != base.materialization_sha256
    assert space.space_sha256 == minilm_space().space_sha256


def test_invalid_materialization_is_rejected():
    with pytest.raises(
        RetrievalContractError,
        match="chunk_overlap must be smaller",
    ):
        MaterializationContract(
            schema_version=1,
            chunker_id="chunker",
            chunk_size=100,
            chunk_overlap=100,
            payload_schema_version="v1",
        )


def test_collection_name_is_derived_only_from_full_space_hash():
    space = minilm_space()
    name = collection_name_for_space(space.space_sha256)

    assert name == f"modai_space_{space.space_sha256[:20]}"
    assert len(name) <= 64
    assert name.replace("_", "").isalnum()

    with pytest.raises(RetrievalContractError, match="SHA-256"):
        collection_name_for_space("../../customer-data")


def test_authorized_read_scope_requires_complete_tenant_scope():
    generation_id = UUID("00000000-0000-0000-0000-000000000001")

    scope = AuthorizedTenantGeneration(
        organization_id=1,
        workspace_id=2,
        knowledge_base_ids=(3, 4),
        generation_id=generation_id,
    )

    assert scope.knowledge_base_ids == (3, 4)

    with pytest.raises(
        RetrievalScopeError,
        match="must not be empty",
    ):
        AuthorizedTenantGeneration(
            organization_id=1,
            workspace_id=2,
            knowledge_base_ids=(),
            generation_id=generation_id,
        )


def test_read_and_write_scopes_are_distinct_types():
    generation_id = UUID("00000000-0000-0000-0000-000000000001")

    read_scope = AuthorizedTenantGeneration(
        organization_id=1,
        workspace_id=2,
        knowledge_base_ids=(3,),
        generation_id=generation_id,
    )
    write_scope = GenerationWriteScope(
        organization_id=1,
        workspace_id=2,
        generation_id=generation_id,
    )

    assert type(read_scope) is not type(write_scope)
    assert not hasattr(write_scope, "collection_name")


def test_resolved_index_rejects_wrong_collection_binding():
    generation_id = UUID("00000000-0000-0000-0000-000000000001")
    scope = AuthorizedTenantGeneration(
        organization_id=1,
        workspace_id=2,
        knowledge_base_ids=(3,),
        generation_id=generation_id,
    )

    with pytest.raises(
        RetrievalCompatibilityError,
        match="collection does not match",
    ):
        ResolvedRetrievalIndex(
            scope=scope,
            space=minilm_space(),
            materialization=materialization(),
            collection_name="rag_documents",
            assignment_epoch=1,
        )


def test_resolved_index_accepts_exact_space_collection():
    generation_id = UUID("00000000-0000-0000-0000-000000000001")
    space = minilm_space()
    scope = AuthorizedTenantGeneration(
        organization_id=1,
        workspace_id=2,
        knowledge_base_ids=(3,),
        generation_id=generation_id,
    )

    resolved = ResolvedRetrievalIndex(
        scope=scope,
        space=space,
        materialization=materialization(),
        collection_name=collection_name_for_space(space.space_sha256),
        assignment_epoch=1,
    )

    assert resolved.scope.generation_id == generation_id


def test_fail_closed_contract_guards():
    mini = minilm_space()
    bge = bge_space()
    material = materialization()

    with pytest.raises(
        RetrievalCompatibilityError,
        match="embedding-space",
    ):
        require_space_match(mini, bge)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="materialization",
    ):
        require_materialization_match(
            material,
            replace(material, chunk_size=800),
        )

    with pytest.raises(
        RetrievalCompatibilityError,
        match="generation",
    ):
        require_generation_match(
            UUID("00000000-0000-0000-0000-000000000001"),
            UUID("00000000-0000-0000-0000-000000000002"),
        )


def test_vector_validation_rejects_wrong_dimension_nonfinite_and_non_normalized():
    small_space = replace(minilm_space(), dimensions=3)

    validate_vector([1.0, 0.0, 0.0], small_space)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="dimension mismatch",
    ):
        validate_vector([1.0, 0.0], small_space)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="non-finite",
    ):
        validate_vector([float("nan"), 0.0, 0.0], small_space)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="not normalized",
    ):
        validate_vector([0.5, 0.0, 0.0], small_space)


def test_legacy_collection_is_explicitly_unverified_not_a_generation():
    legacy = LegacyUnverifiedRetrieval()

    assert legacy.mode == "legacy_unverified"
    assert legacy.collection_name == "rag_documents"
    assert not hasattr(legacy, "generation_id")
    assert not hasattr(legacy, "space")


def test_existing_production_defaults_remain_unchanged():
    settings = Settings(_env_file=None)

    assert settings.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert settings.rag_top_k == 3
    assert settings.ollama_model == "modAIJet:latest"
    assert QdrantService.collection_name == "rag_documents"


def test_authorized_scope_normalizes_mutable_input_to_immutable_tuple():
    generation_id = UUID("00000000-0000-0000-0000-000000000001")
    original = [3, 4]

    scope = AuthorizedTenantGeneration(
        organization_id=1,
        workspace_id=2,
        knowledge_base_ids=original,
        generation_id=generation_id,
    )

    assert scope.knowledge_base_ids == (3, 4)
    assert isinstance(scope.knowledge_base_ids, tuple)

    original.append(5)
    assert scope.knowledge_base_ids == (3, 4)


def test_authorized_scope_rejects_duplicate_knowledge_bases():
    generation_id = UUID("00000000-0000-0000-0000-000000000001")

    with pytest.raises(
        RetrievalScopeError,
        match="must not contain duplicates",
    ):
        AuthorizedTenantGeneration(
            organization_id=1,
            workspace_id=2,
            knowledge_base_ids=(3, 3),
            generation_id=generation_id,
        )


def test_legacy_identity_cannot_be_overridden_by_caller():
    with pytest.raises(TypeError):
        LegacyUnverifiedRetrieval(collection_name="customer_vectors")


def test_vector_validation_wraps_invalid_numeric_input_fail_closed():
    small_space = replace(minilm_space(), dimensions=3)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="invalid numeric",
    ):
        validate_vector(["not-a-number", 0.0, 0.0], small_space)


def test_max_input_tokens_is_part_of_space_identity():
    base = minilm_space()

    changed = replace(
        base,
        max_input_tokens=512,
    )

    assert changed.space_sha256 != base.space_sha256


def test_invalid_max_input_tokens_is_rejected():
    with pytest.raises(
        RetrievalContractError,
        match="max_input_tokens must be positive",
    ):
        replace(
            minilm_space(),
            max_input_tokens=0,
        )


def test_bge_candidate_registry_is_exact_pinned_and_inactive():
    from app.services.rag.retrieval_contract_registry import (
        BALANCED_MULTILINGUAL_BGE_M3_V1,
        BGE_M3_MODEL_ID,
        BGE_M3_REVISION,
        get_reviewed_candidate,
    )

    candidate = get_reviewed_candidate(
        "balanced-multilingual",
        1,
    )

    assert candidate is BALANCED_MULTILINGUAL_BGE_M3_V1
    assert candidate.profile_id == "balanced-multilingual"
    assert candidate.profile_version == 1
    assert candidate.runtime_enabled is False
    assert candidate.selectable is False

    assert candidate.space.model_id == BGE_M3_MODEL_ID
    assert candidate.space.model_id == "BAAI/bge-m3"
    assert candidate.space.model_revision == BGE_M3_REVISION
    assert candidate.space.model_revision == (
        "31e47391fcbda65be526abe98e646b3c6cd845a8"
    )

    assert candidate.space.dimensions == 1024
    assert candidate.space.max_input_tokens == 8192
    assert candidate.space.query_preprocessing == "identity-no-prefix-v1"
    assert candidate.space.passage_preprocessing == "identity-no-prefix-v1"
    assert candidate.space.normalize_embeddings is True
    assert candidate.space.distance_metric == "cosine"


def test_current_legacy_minilm_is_not_falsely_registered_as_verified():
    from app.services.rag.retrieval_contract_registry import (
        get_reviewed_candidate,
    )

    assert get_reviewed_candidate("english-optimized", 1) is None
    assert get_reviewed_candidate("compact-multilingual", 1) is None


def test_unknown_candidate_is_not_guessed():
    from app.services.rag.retrieval_contract_registry import (
        get_reviewed_candidate,
    )

    assert get_reviewed_candidate("unknown-profile", 1) is None
    assert get_reviewed_candidate("balanced-multilingual", 999) is None


def test_reviewed_registry_cannot_enable_runtime_candidate():
    from app.services.rag.retrieval_contract_registry import (
        ReviewedEmbeddingCandidate,
    )

    with pytest.raises(ValueError, match="cannot enable runtime"):
        ReviewedEmbeddingCandidate(
            profile_id="unsafe",
            profile_version=1,
            space=bge_space(),
            runtime_enabled=True,
        )


def test_reviewed_registry_cannot_make_candidate_selectable():
    from app.services.rag.retrieval_contract_registry import (
        ReviewedEmbeddingCandidate,
    )

    with pytest.raises(ValueError, match="cannot expose selectable"):
        ReviewedEmbeddingCandidate(
            profile_id="unsafe",
            profile_version=1,
            space=bge_space(),
            selectable=True,
        )
