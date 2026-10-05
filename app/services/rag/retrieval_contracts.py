"""Immutable retrieval/index contracts for future generation-aware retrieval.

This module is foundation-only. It does not activate a retrieval profile,
change the current MiniLM serving path, create Qdrant collections, or perform
document reindexing.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from typing import Literal, Sequence
from uuid import UUID


DistanceMetric = Literal["cosine", "dot", "euclid"]

_SPACE_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_COLLECTION_RE = re.compile(r"^[a-z0-9_]+$")


class RetrievalContractError(ValueError):
    """Base error for invalid retrieval contract state."""


class RetrievalCompatibilityError(RetrievalContractError):
    """Raised when two retrieval/index identities are incompatible."""


class RetrievalScopeError(RetrievalContractError):
    """Raised when a tenant/generation scope is incomplete or invalid."""


def _require_nonempty(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise RetrievalContractError(f"{field_name} must be non-empty")


def _canonical_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class EmbeddingSpaceContract:
    """Immutable identity for one compatible embedding vector space."""

    schema_version: int
    model_id: str
    model_revision: str
    dimensions: int
    max_input_tokens: int
    query_preprocessing: str
    passage_preprocessing: str
    tokenizer_identity: str
    normalize_embeddings: bool
    distance_metric: DistanceMetric
    vector_name: str = "default"

    def __post_init__(self) -> None:
        if self.schema_version <= 0:
            raise RetrievalContractError("schema_version must be positive")

        for field_name in (
            "model_id",
            "model_revision",
            "query_preprocessing",
            "passage_preprocessing",
            "tokenizer_identity",
            "vector_name",
        ):
            _require_nonempty(getattr(self, field_name), field_name)

        if self.dimensions <= 0:
            raise RetrievalContractError("dimensions must be positive")

        if self.max_input_tokens <= 0:
            raise RetrievalContractError("max_input_tokens must be positive")

        if self.distance_metric not in {"cosine", "dot", "euclid"}:
            raise RetrievalContractError("unsupported distance metric")

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "model_id": self.model_id,
            "model_revision": self.model_revision,
            "dimensions": self.dimensions,
            "max_input_tokens": self.max_input_tokens,
            "query_preprocessing": self.query_preprocessing,
            "passage_preprocessing": self.passage_preprocessing,
            "tokenizer_identity": self.tokenizer_identity,
            "normalize_embeddings": self.normalize_embeddings,
            "distance_metric": self.distance_metric,
            "vector_name": self.vector_name,
        }

    @property
    def space_sha256(self) -> str:
        return _canonical_sha256(self.canonical_payload())


@dataclass(frozen=True, slots=True)
class MaterializationContract:
    """Immutable identity for how source content becomes indexed chunks."""

    schema_version: int
    chunker_id: str
    chunk_size: int
    chunk_overlap: int
    payload_schema_version: str
    index_format: str = "dense-single-vector-v1"

    def __post_init__(self) -> None:
        if self.schema_version <= 0:
            raise RetrievalContractError("schema_version must be positive")

        for field_name in (
            "chunker_id",
            "payload_schema_version",
            "index_format",
        ):
            _require_nonempty(getattr(self, field_name), field_name)

        if self.chunk_size <= 0:
            raise RetrievalContractError("chunk_size must be positive")

        if self.chunk_overlap < 0:
            raise RetrievalContractError("chunk_overlap must not be negative")

        if self.chunk_overlap >= self.chunk_size:
            raise RetrievalContractError(
                "chunk_overlap must be smaller than chunk_size"
            )

    def canonical_payload(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "chunker_id": self.chunker_id,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "payload_schema_version": self.payload_schema_version,
            "index_format": self.index_format,
        }

    @property
    def materialization_sha256(self) -> str:
        return _canonical_sha256(self.canonical_payload())


def collection_name_for_space(space_sha256: str) -> str:
    """Derive a safe physical collection name from a trusted full space hash."""

    if not _SPACE_HASH_RE.fullmatch(space_sha256):
        raise RetrievalContractError(
            "space_sha256 must be a lowercase 64-character SHA-256 hex digest"
        )

    collection_name = f"modai_space_{space_sha256[:20]}"

    if len(collection_name) > 64 or not _COLLECTION_RE.fullmatch(collection_name):
        raise RetrievalContractError("derived collection name is invalid")

    return collection_name


@dataclass(frozen=True, slots=True)
class AuthorizedTenantGeneration:
    """Already-authorized read scope for one workspace generation."""

    organization_id: int
    workspace_id: int
    knowledge_base_ids: tuple[int, ...]
    generation_id: UUID

    def __post_init__(self) -> None:
        if self.organization_id <= 0:
            raise RetrievalScopeError("organization_id must be positive")

        if self.workspace_id <= 0:
            raise RetrievalScopeError("workspace_id must be positive")

        normalized_kb_ids = tuple(self.knowledge_base_ids)
        object.__setattr__(self, "knowledge_base_ids", normalized_kb_ids)

        if not normalized_kb_ids:
            raise RetrievalScopeError("knowledge_base_ids must not be empty")

        if any(value <= 0 for value in normalized_kb_ids):
            raise RetrievalScopeError(
                "knowledge_base_ids must contain positive IDs"
            )

        if len(set(normalized_kb_ids)) != len(normalized_kb_ids):
            raise RetrievalScopeError(
                "knowledge_base_ids must not contain duplicates"
            )


@dataclass(frozen=True, slots=True)
class GenerationWriteScope:
    """Trusted migration/indexing write scope.

    This type intentionally does not accept an arbitrary collection name.
    """

    organization_id: int
    workspace_id: int
    generation_id: UUID

    def __post_init__(self) -> None:
        if self.organization_id <= 0:
            raise RetrievalScopeError("organization_id must be positive")

        if self.workspace_id <= 0:
            raise RetrievalScopeError("workspace_id must be positive")


@dataclass(frozen=True, slots=True)
class ResolvedRetrievalIndex:
    """One immutable retrieval decision carried through an entire request."""

    scope: AuthorizedTenantGeneration
    space: EmbeddingSpaceContract
    materialization: MaterializationContract
    collection_name: str
    assignment_epoch: int

    def __post_init__(self) -> None:
        if self.assignment_epoch < 0:
            raise RetrievalContractError(
                "assignment_epoch must not be negative"
            )

        expected_collection = collection_name_for_space(
            self.space.space_sha256
        )
        if self.collection_name != expected_collection:
            raise RetrievalCompatibilityError(
                "collection does not match the resolved embedding space"
            )


@dataclass(frozen=True, slots=True)
class ResolvedGenerationWriteIndex:
    """Immutable trusted identity for one generation-scoped write target.

    Construction is intended for a future privileged migration resolver.
    The collection name remains bound to the exact embedding-space hash.
    """

    scope: GenerationWriteScope
    space: EmbeddingSpaceContract
    materialization: MaterializationContract
    collection_name: str

    def __post_init__(self) -> None:
        expected_collection = collection_name_for_space(
            self.space.space_sha256
        )

        if self.collection_name != expected_collection:
            raise RetrievalCompatibilityError(
                "collection does not match the resolved embedding space"
            )


@dataclass(frozen=True, slots=True)
class LegacyUnverifiedRetrieval:
    """Explicit representation of the current unversioned legacy index.

    The identity is intentionally fixed so callers cannot turn legacy mode
    into a generic arbitrary-collection escape hatch.
    """

    mode: Literal["legacy_unverified"] = field(
        init=False,
        default="legacy_unverified",
    )
    collection_name: str = field(
        init=False,
        default="rag_documents",
    )


def require_space_match(
    expected: EmbeddingSpaceContract,
    actual: EmbeddingSpaceContract,
) -> None:
    if expected.space_sha256 != actual.space_sha256:
        raise RetrievalCompatibilityError(
            "embedding-space contract mismatch"
        )


def require_materialization_match(
    expected: MaterializationContract,
    actual: MaterializationContract,
) -> None:
    if expected.materialization_sha256 != actual.materialization_sha256:
        raise RetrievalCompatibilityError(
            "materialization contract mismatch"
        )


def require_generation_match(expected: UUID, actual: UUID) -> None:
    if expected != actual:
        raise RetrievalCompatibilityError("index generation mismatch")


def validate_vector(
    vector: Sequence[float],
    space: EmbeddingSpaceContract,
) -> None:
    if len(vector) != space.dimensions:
        raise RetrievalCompatibilityError(
            f"vector dimension mismatch: expected {space.dimensions}"
        )

    try:
        values = [float(value) for value in vector]
    except (TypeError, ValueError, OverflowError) as exc:
        raise RetrievalCompatibilityError(
            "embedding vector contains invalid numeric values"
        ) from exc

    if not all(math.isfinite(value) for value in values):
        raise RetrievalCompatibilityError(
            "embedding vector contains non-finite values"
        )

    if space.normalize_embeddings:
        norm = math.sqrt(sum(value * value for value in values))
        if not math.isclose(norm, 1.0, rel_tol=0.0, abs_tol=1e-4):
            raise RetrievalCompatibilityError(
                "embedding vector is not normalized"
            )
