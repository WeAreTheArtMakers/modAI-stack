"""PostgreSQL guard for Qdrant collection/full-space identity.

A physical Qdrant collection may be shared by many generations only when all
of them refer to the exact same full embedding-space SHA-256.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import IndexGeneration
from app.services.rag.retrieval_contracts import (
    RetrievalCompatibilityError,
    collection_name_for_space,
)


async def assert_collection_space_binding(
    db: AsyncSession,
    *,
    collection_name: str,
    space_sha256: str,
) -> None:
    expected_collection = collection_name_for_space(
        space_sha256
    )

    if collection_name != expected_collection:
        raise RetrievalCompatibilityError(
            "collection does not match full embedding-space identity"
        )

    existing_hashes = set(
        (
            await db.scalars(
                select(
                    IndexGeneration.space_sha256
                )
                .where(
                    IndexGeneration.qdrant_collection
                    == collection_name
                )
                .distinct()
            )
        ).all()
    )

    conflicting = existing_hashes - {
        space_sha256
    }

    if conflicting:
        raise RetrievalCompatibilityError(
            "Qdrant collection-name collision across embedding spaces"
        )
