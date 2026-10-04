"""Reviewed retrieval-contract candidates.

This registry is internal foundation metadata only.

Entries here are NOT automatically:
- active
- selectable
- production-loadable
- authorized for indexing
- authorized for Qdrant collection creation
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from app.services.rag.retrieval_contracts import EmbeddingSpaceContract


BGE_M3_MODEL_ID = "BAAI/bge-m3"
BGE_M3_REVISION = "31e47391fcbda65be526abe98e646b3c6cd845a8"


@dataclass(frozen=True, slots=True)
class ReviewedEmbeddingCandidate:
    """A reviewed embedding-space candidate, not a runtime activation."""

    profile_id: str
    profile_version: int
    space: EmbeddingSpaceContract
    runtime_enabled: bool = False
    selectable: bool = False

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("profile_id must be non-empty")

        if self.profile_version <= 0:
            raise ValueError("profile_version must be positive")

        if self.runtime_enabled:
            raise ValueError(
                "reviewed candidate registry cannot enable runtime profiles"
            )

        if self.selectable:
            raise ValueError(
                "reviewed candidate registry cannot expose selectable profiles"
            )


BALANCED_MULTILINGUAL_BGE_M3_V1 = ReviewedEmbeddingCandidate(
    profile_id="balanced-multilingual",
    profile_version=1,
    space=EmbeddingSpaceContract(
        schema_version=1,
        model_id=BGE_M3_MODEL_ID,
        model_revision=BGE_M3_REVISION,
        dimensions=1024,
        max_input_tokens=8192,
        query_preprocessing="identity-no-prefix-v1",
        passage_preprocessing="identity-no-prefix-v1",
        tokenizer_identity=f"huggingface-revision:{BGE_M3_REVISION}",
        normalize_embeddings=True,
        distance_metric="cosine",
        vector_name="dense",
    ),
)


_CANDIDATES: Mapping[
    tuple[str, int],
    ReviewedEmbeddingCandidate,
] = MappingProxyType(
    {
        (
            BALANCED_MULTILINGUAL_BGE_M3_V1.profile_id,
            BALANCED_MULTILINGUAL_BGE_M3_V1.profile_version,
        ): BALANCED_MULTILINGUAL_BGE_M3_V1,
    }
)


def get_reviewed_candidate(
    profile_id: str,
    profile_version: int,
) -> ReviewedEmbeddingCandidate | None:
    """Return reviewed metadata only; never performs runtime activation."""

    return _CANDIDATES.get((profile_id, profile_version))


def reviewed_candidates() -> tuple[ReviewedEmbeddingCandidate, ...]:
    return tuple(_CANDIDATES.values())
