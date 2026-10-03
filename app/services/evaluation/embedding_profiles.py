"""Pinned, evaluation-only embedding profile contracts.

This module deliberately does not alter the production embedding setting or
runtime. It describes input preprocessing and vector-space identity for
isolated retrieval experiments.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from collections.abc import Iterable, Sequence


MINILM_PROFILE_ID = "english-optimized-baseline"
MINILM_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
MINILM_REVISION = "1110a243fdf4706b3f48f1d95db1a4f5529b4d41"

E5_PROFILE_ID = "compact-multilingual-candidate"
E5_MODEL_ID = "intfloat/multilingual-e5-small"
E5_REVISION = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
E5_BASE_PROFILE_ID = "compact-multilingual-e5-base-candidate"
E5_BASE_MODEL_ID = "intfloat/multilingual-e5-base"
E5_BASE_REVISION = "d128750597153bb5987e10b1c3493a34e5a4502a"


@dataclass(frozen=True)
class EmbeddingProfileSpec:
    profile_id: str
    model_id: str
    revision: str
    license: str
    dimensions: int
    max_input_tokens: int
    language_scope: str
    query_prefix: str = ""
    passage_prefix: str = ""

    def preprocess_query(self, text: str) -> str:
        return f"{self.query_prefix}{text}"

    def preprocess_passage(self, text: str) -> str:
        return f"{self.passage_prefix}{text}"

    @property
    def vector_space_identity(self) -> str:
        """Identify the full embedding space, including asymmetric prefixes."""
        values = {
            "model_id": self.model_id,
            "revision": self.revision,
            "dimensions": self.dimensions,
            "query_prefix": self.query_prefix,
            "passage_prefix": self.passage_prefix,
        }
        canonical = json.dumps(values, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @property
    def collection_name(self) -> str:
        return f"embedding_benchmark_{self.vector_space_identity[:16]}"

    def safe_metadata(self) -> dict[str, str | int]:
        """Return provenance suitable for an aggregate report; never a local path."""
        return {
            "profile_id": self.profile_id,
            "model_id": self.model_id,
            "revision": self.revision,
            "license": self.license,
            "dimensions": self.dimensions,
            "max_input_tokens": self.max_input_tokens,
            "language_scope": self.language_scope,
            "query_prefix": self.query_prefix,
            "passage_prefix": self.passage_prefix,
            "vector_space_identity": self.vector_space_identity,
        }


MINILM_BASELINE = EmbeddingProfileSpec(
    profile_id=MINILM_PROFILE_ID,
    model_id=MINILM_MODEL_ID,
    revision=MINILM_REVISION,
    license="Apache-2.0",
    dimensions=384,
    max_input_tokens=256,
    language_scope="English-focused",
)

MULTILINGUAL_E5_SMALL = EmbeddingProfileSpec(
    profile_id=E5_PROFILE_ID,
    model_id=E5_MODEL_ID,
    revision=E5_REVISION,
    license="MIT",
    dimensions=384,
    max_input_tokens=512,
    language_scope="94 languages (upstream model card)",
    query_prefix="query: ",
    passage_prefix="passage: ",
)

MULTILINGUAL_E5_BASE = EmbeddingProfileSpec(
    profile_id=E5_BASE_PROFILE_ID,
    model_id=E5_BASE_MODEL_ID,
    revision=E5_BASE_REVISION,
    license="MIT",
    dimensions=768,
    max_input_tokens=512,
    language_scope="Multilingual (upstream model card)",
    query_prefix="query: ",
    passage_prefix="passage: ",
)


class EmbeddingSpaceMismatchError(ValueError):
    """Raised if vectors or an index are used with a different embedding space."""


def assert_same_embedding_space(
    index_profile: EmbeddingProfileSpec,
    requested_profile: EmbeddingProfileSpec,
) -> None:
    if index_profile.vector_space_identity != requested_profile.vector_space_identity:
        raise EmbeddingSpaceMismatchError(
            "embedding profile/revision/preprocessing does not match the isolated index"
        )


def validate_vector(vector: Sequence[float], profile: EmbeddingProfileSpec) -> None:
    if len(vector) != profile.dimensions:
        raise EmbeddingSpaceMismatchError(
            f"embedding dimension mismatch for {profile.profile_id}: "
            f"expected {profile.dimensions}, got {len(vector)}"
        )


def validate_vectors(
    vectors: Iterable[Sequence[float]], profile: EmbeddingProfileSpec
) -> None:
    for vector in vectors:
        validate_vector(vector, profile)


class EmbeddingSpaceGuard:
    """Bind an isolated index to one immutable model/revision/input contract."""

    def __init__(self, index_profile: EmbeddingProfileSpec):
        self._index_profile = index_profile

    def validate_vector(
        self, requested_profile: EmbeddingProfileSpec, vector: Sequence[float]
    ) -> None:
        assert_same_embedding_space(self._index_profile, requested_profile)
        validate_vector(vector, self._index_profile)

    def validate_vectors(
        self,
        requested_profile: EmbeddingProfileSpec,
        vectors: Iterable[Sequence[float]],
    ) -> None:
        assert_same_embedding_space(self._index_profile, requested_profile)
        validate_vectors(vectors, self._index_profile)
