from types import SimpleNamespace

import pytest

from app.services.rag.generation_collection_binding import (
    assert_collection_space_binding,
)
from app.services.rag.retrieval_contracts import (
    RetrievalCompatibilityError,
    collection_name_for_space,
)


class ScalarResult:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class FakeDb:
    def __init__(self, values):
        self.values = values

    async def scalars(self, _statement):
        return ScalarResult(self.values)


@pytest.mark.asyncio
async def test_collection_binding_allows_unused_collection():
    space_sha256 = "a" * 64
    collection = collection_name_for_space(
        space_sha256
    )

    await assert_collection_space_binding(
        FakeDb([]),
        collection_name=collection,
        space_sha256=space_sha256,
    )


@pytest.mark.asyncio
async def test_collection_binding_allows_same_full_space_reuse():
    space_sha256 = "a" * 64
    collection = collection_name_for_space(
        space_sha256
    )

    await assert_collection_space_binding(
        FakeDb([space_sha256]),
        collection_name=collection,
        space_sha256=space_sha256,
    )


@pytest.mark.asyncio
async def test_collection_binding_rejects_truncated_name_collision():
    requested = "a" * 64

    # Same first 20 hex chars -> same physical collection name,
    # but a different full embedding-space identity.
    existing = ("a" * 20) + ("b" * 44)

    assert existing != requested

    collection = collection_name_for_space(
        requested
    )

    assert collection == collection_name_for_space(
        existing
    )

    with pytest.raises(
        RetrievalCompatibilityError,
        match="collection-name collision",
    ):
        await assert_collection_space_binding(
            FakeDb([existing]),
            collection_name=collection,
            space_sha256=requested,
        )


@pytest.mark.asyncio
async def test_collection_binding_rejects_arbitrary_collection_name():
    with pytest.raises(
        RetrievalCompatibilityError,
        match="full embedding-space identity",
    ):
        await assert_collection_space_binding(
            FakeDb([]),
            collection_name="customer_vectors",
            space_sha256="a" * 64,
        )
