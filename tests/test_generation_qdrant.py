from types import SimpleNamespace
from uuid import UUID

import pytest
from qdrant_client.http import models

from app.services.rag.generation_qdrant import (
    GenerationQdrantAdapter,
)
from app.services.rag.retrieval_contracts import (
    AuthorizedTenantGeneration,
    EmbeddingSpaceContract,
    GenerationWriteScope,
    MaterializationContract,
    ResolvedGenerationWriteIndex,
    ResolvedRetrievalIndex,
    RetrievalCompatibilityError,
    collection_name_for_space,
)


GENERATION_ID = UUID(
    "00000000-0000-0000-0000-000000000001"
)


def space(
    *,
    model_id="test-model-a",
    vector_name="dense",
):
    return EmbeddingSpaceContract(
        schema_version=1,
        model_id=model_id,
        model_revision=f"{model_id}-revision",
        dimensions=3,
        max_input_tokens=128,
        query_preprocessing="identity-v1",
        passage_preprocessing="identity-v1",
        tokenizer_identity=f"{model_id}-tokenizer",
        normalize_embeddings=True,
        distance_metric="cosine",
        vector_name=vector_name,
    )


def materialization():
    return MaterializationContract(
        schema_version=1,
        chunker_id="modai-chunker-v1",
        chunk_size=700,
        chunk_overlap=100,
        payload_schema_version="rag-payload-v1",
    )


def read_index():
    item_space = space()

    return ResolvedRetrievalIndex(
        scope=AuthorizedTenantGeneration(
            organization_id=1,
            workspace_id=2,
            knowledge_base_ids=(3, 4),
            generation_id=GENERATION_ID,
        ),
        space=item_space,
        materialization=materialization(),
        collection_name=collection_name_for_space(
            item_space.space_sha256
        ),
        assignment_epoch=7,
    )


def write_index():
    item_space = space()

    return ResolvedGenerationWriteIndex(
        scope=GenerationWriteScope(
            organization_id=1,
            workspace_id=2,
            generation_id=GENERATION_ID,
        ),
        space=item_space,
        materialization=materialization(),
        collection_name=collection_name_for_space(
            item_space.space_sha256
        ),
    )


class FakeClient:
    def __init__(self, index):
        self.index = index
        self.calls = []
        self.search_hits = []
        self.scroll_records = []
        self.collection_exists = True
        self.payload_schema = {}

    async def get_collection(self, collection_name):
        self.calls.append(
            ("get_collection", collection_name)
        )

        return SimpleNamespace(
            config=SimpleNamespace(
                params=SimpleNamespace(
                    vectors={
                        self.index.space.vector_name:
                        models.VectorParams(
                            size=self.index.space.dimensions,
                            distance=models.Distance.COSINE,
                        )
                    }
                )
            ),
            payload_schema=self.payload_schema,
        )

    async def get_collections(self):
        self.calls.append(("get_collections",))

        collections = (
            [SimpleNamespace(name=self.index.collection_name)]
            if self.collection_exists
            else []
        )

        return SimpleNamespace(
            collections=collections
        )

    async def create_collection(self, **kwargs):
        self.calls.append(
            ("create_collection", kwargs)
        )
        return True

    async def create_payload_index(self, **kwargs):
        self.calls.append(
            ("create_payload_index", kwargs)
        )

        self.payload_schema[
            kwargs["field_name"]
        ] = SimpleNamespace(
            data_type=kwargs["field_schema"]
        )

    async def search(self, **kwargs):
        self.calls.append(
            ("search", kwargs)
        )
        return self.search_hits

    async def upsert(self, **kwargs):
        self.calls.append(
            ("upsert", kwargs)
        )

    async def delete(self, **kwargs):
        self.calls.append(
            ("delete", kwargs)
        )

    async def count(self, **kwargs):
        self.calls.append(
            ("count", kwargs)
        )
        return SimpleNamespace(count=4)

    async def scroll(self, **kwargs):
        self.calls.append(
            ("scroll", kwargs)
        )
        return self.scroll_records, None


def condition_map(query_filter):
    result = {}

    for condition in query_filter.must:
        match = condition.match

        if hasattr(match, "value"):
            result[condition.key] = match.value
        elif hasattr(match, "any"):
            result[condition.key] = tuple(match.any)

    return result


def valid_payload(index, **updates):
    payload = {
        "organization_id": 1,
        "workspace_id": 2,
        "knowledge_base_id": 3,
        "document_id": 10,
        "document_version": 2,
        "source_revision": 5,
        "chunk_index": 0,
        "index_generation_id": str(
            GENERATION_ID
        ),
        "space_sha256": (
            index.space.space_sha256
        ),
        "materialization_sha256": (
            index.materialization
            .materialization_sha256
        ),
        "payload_schema_version": (
            index.materialization
            .payload_schema_version
        ),
        "content_hash": "a" * 64,
        "filename": "test.txt",
        "text": "safe text",
    }

    payload.update(updates)
    return payload


def test_generation_point_id_is_deterministic_and_contract_scoped():
    index = write_index()

    first = GenerationQdrantAdapter.point_id(
        index,
        document_id=10,
        document_version=2,
        chunk_index=0,
    )

    second = GenerationQdrantAdapter.point_id(
        index,
        document_id=10,
        document_version=2,
        chunk_index=0,
    )

    changed_chunk = GenerationQdrantAdapter.point_id(
        index,
        document_id=10,
        document_version=2,
        chunk_index=1,
    )

    assert first == second
    assert first != changed_chunk


@pytest.mark.asyncio
async def test_wrong_embedding_space_fails_before_qdrant_search():
    index = read_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    wrong_space = space(
        model_id="different-model"
    )

    with pytest.raises(
        RetrievalCompatibilityError,
        match="embedding-space",
    ):
        await adapter.search(
            index,
            query_space=wrong_space,
            vector=[1.0, 0.0, 0.0],
            limit=3,
        )

    assert client.calls == []


@pytest.mark.asyncio
async def test_generation_search_builds_mandatory_fail_closed_filter():
    index = read_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    client.search_hits = [
        SimpleNamespace(
            score=0.9,
            payload=valid_payload(index),
        )
    ]

    hits = await adapter.search(
        index,
        query_space=index.space,
        vector=[1.0, 0.0, 0.0],
        limit=3,
        candidate_limit=5,
    )

    assert len(hits) == 1

    search_call = next(
        call
        for call in client.calls
        if call[0] == "search"
    )[1]

    values = condition_map(
        search_call["query_filter"]
    )

    assert values["organization_id"] == 1
    assert values["workspace_id"] == 2
    assert values["knowledge_base_id"] == (3, 4)
    assert values["index_generation_id"] == str(
        GENERATION_ID
    )
    assert (
        values["space_sha256"]
        == index.space.space_sha256
    )
    assert (
        values["materialization_sha256"]
        == index.materialization.materialization_sha256
    )

    assert "is_active" not in values

    assert search_call["limit"] == 5
    assert (
        search_call["query_vector"].name
        == index.space.vector_name
    )


@pytest.mark.asyncio
async def test_generation_search_rejects_payload_outside_scope():
    index = read_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    client.search_hits = [
        SimpleNamespace(
            score=0.9,
            payload=valid_payload(
                index,
                workspace_id=999,
            ),
        )
    ]

    with pytest.raises(
        RetrievalCompatibilityError,
        match="workspace_id mismatch",
    ):
        await adapter.search(
            index,
            query_space=index.space,
            vector=[1.0, 0.0, 0.0],
            limit=3,
        )


@pytest.mark.asyncio
async def test_candidate_limit_is_bounded():
    index = read_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="candidate limit",
    ):
        await adapter.search(
            index,
            query_space=index.space,
            vector=[1.0, 0.0, 0.0],
            limit=3,
            candidate_limit=51,
        )


@pytest.mark.asyncio
async def test_upsert_uses_named_vector_and_complete_generation_payload():
    index = write_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    point_ids = await adapter.upsert_document(
        index,
        vector_space=index.space,
        knowledge_base_id=3,
        document_id=10,
        document_version=2,
        source_revision=5,
        content_hash="a" * 64,
        filename="source.txt",
        chunks=["first", "second"],
        vectors=[
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
        ],
    )

    assert len(point_ids) == 2

    upsert_call = next(
        call
        for call in client.calls
        if call[0] == "upsert"
    )[1]

    assert (
        upsert_call["collection_name"]
        == index.collection_name
    )

    first = upsert_call["points"][0]

    assert set(first.vector) == {
        index.space.vector_name
    }

    payload = first.payload

    assert payload["organization_id"] == 1
    assert payload["workspace_id"] == 2
    assert payload["knowledge_base_id"] == 3
    assert payload["document_id"] == 10
    assert payload["document_version"] == 2
    assert payload["source_revision"] == 5
    assert payload["chunk_index"] == 0
    assert payload["index_generation_id"] == str(
        GENERATION_ID
    )
    assert (
        payload["space_sha256"]
        == index.space.space_sha256
    )
    assert (
        payload["materialization_sha256"]
        == index.materialization.materialization_sha256
    )
    assert (
        payload["payload_schema_version"]
        == index.materialization.payload_schema_version
    )

    assert "is_active" not in payload


@pytest.mark.asyncio
async def test_delete_is_generation_and_document_scoped():
    index = write_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    await adapter.delete_document(
        index,
        document_id=10,
        document_version=2,
    )

    delete_call = next(
        call
        for call in client.calls
        if call[0] == "delete"
    )[1]

    values = condition_map(
        delete_call[
            "points_selector"
        ].filter
    )

    assert values["organization_id"] == 1
    assert values["workspace_id"] == 2
    assert values["document_id"] == 10
    assert values["document_version"] == 2
    assert values["index_generation_id"] == str(
        GENERATION_ID
    )
    assert (
        values["space_sha256"]
        == index.space.space_sha256
    )
    assert (
        values["materialization_sha256"]
        == index.materialization.materialization_sha256
    )


@pytest.mark.asyncio
async def test_collection_contract_mismatch_fails_closed():
    index = read_index()

    class WrongCollectionClient(FakeClient):
        async def get_collection(self, collection_name):
            self.calls.append(
                ("get_collection", collection_name)
            )

            return SimpleNamespace(
                config=SimpleNamespace(
                    params=SimpleNamespace(
                        vectors={
                            index.space.vector_name:
                            models.VectorParams(
                                size=999,
                                distance=models.Distance.COSINE,
                            )
                        }
                    )
                )
            )

    client = WrongCollectionClient(index)
    adapter = GenerationQdrantAdapter(client)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="dimension mismatch",
    ):
        await adapter.search(
            index,
            query_space=index.space,
            vector=[1.0, 0.0, 0.0],
            limit=3,
        )

    assert not any(
        call[0] == "search"
        for call in client.calls
    )


@pytest.mark.asyncio
async def test_collection_creation_uses_exact_named_space_and_payload_indexes():
    index = write_index()
    client = FakeClient(index)
    client.collection_exists = False

    adapter = GenerationQdrantAdapter(client)

    created = await adapter.create_collection(
        index
    )

    assert created is True

    create_call = next(
        call
        for call in client.calls
        if call[0] == "create_collection"
    )[1]

    assert (
        create_call["collection_name"]
        == index.collection_name
    )

    vectors = create_call["vectors_config"]

    assert set(vectors) == {
        index.space.vector_name
    }
    assert (
        vectors[index.space.vector_name].size
        == index.space.dimensions
    )

    indexed_fields = {
        call[1]["field_name"]
        for call in client.calls
        if call[0] == "create_payload_index"
    }

    assert {
        "organization_id",
        "workspace_id",
        "knowledge_base_id",
        "document_id",
        "document_version",
        "source_revision",
        "index_generation_id",
        "space_sha256",
        "materialization_sha256",
    }.issubset(indexed_fields)


@pytest.mark.asyncio
async def test_count_and_scroll_are_generation_scoped():
    index = write_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    client.scroll_records = [
        SimpleNamespace(
            payload=valid_payload(index)
        )
    ]

    assert await adapter.count_generation(index) == 4

    records, next_offset = (
        await adapter.scroll_generation(
            index,
            limit=20,
        )
    )

    assert len(records) == 1
    assert next_offset is None

    count_call = next(
        call
        for call in client.calls
        if call[0] == "count"
    )[1]

    values = condition_map(
        count_call["count_filter"]
    )

    assert values["organization_id"] == 1
    assert values["workspace_id"] == 2
    assert values["index_generation_id"] == str(
        GENERATION_ID
    )


def test_generation_point_id_changes_with_physical_index_identity():
    base = write_index()

    second_generation = ResolvedGenerationWriteIndex(
        scope=GenerationWriteScope(
            organization_id=1,
            workspace_id=2,
            generation_id=UUID(
                "00000000-0000-0000-0000-000000000002"
            ),
        ),
        space=base.space,
        materialization=base.materialization,
        collection_name=base.collection_name,
    )

    changed_space = space(
        model_id="same-dimension-other-space"
    )
    other_space = ResolvedGenerationWriteIndex(
        scope=base.scope,
        space=changed_space,
        materialization=base.materialization,
        collection_name=collection_name_for_space(
            changed_space.space_sha256
        ),
    )

    changed_materialization = MaterializationContract(
        schema_version=1,
        chunker_id="modai-chunker-v1",
        chunk_size=800,
        chunk_overlap=100,
        payload_schema_version="rag-payload-v1",
    )
    other_materialization = ResolvedGenerationWriteIndex(
        scope=base.scope,
        space=base.space,
        materialization=changed_materialization,
        collection_name=base.collection_name,
    )

    def point(index):
        return GenerationQdrantAdapter.point_id(
            index,
            document_id=10,
            document_version=2,
            chunk_index=0,
        )

    base_id = point(base)

    assert point(second_generation) != base_id
    assert point(other_space) != base_id
    assert point(other_materialization) != base_id


@pytest.mark.asyncio
async def test_real_qdrant_generation_isolation_and_named_vectors():
    from qdrant_client import AsyncQdrantClient

    client = AsyncQdrantClient(":memory:")

    try:
        write = write_index()
        adapter = GenerationQdrantAdapter(client)

        created = await adapter.create_collection(write)
        assert created is True

        await adapter.upsert_document(
            write,
            vector_space=write.space,
            knowledge_base_id=3,
            document_id=10,
            document_version=1,
            source_revision=1,
            content_hash="a" * 64,
            filename="allowed.txt",
            chunks=["allowed source"],
            vectors=[[1.0, 0.0, 0.0]],
        )

        await adapter.upsert_document(
            write,
            vector_space=write.space,
            knowledge_base_id=4,
            document_id=20,
            document_version=1,
            source_revision=1,
            content_hash="b" * 64,
            filename="other-kb.txt",
            chunks=["other knowledge base"],
            vectors=[[1.0, 0.0, 0.0]],
        )

        read = ResolvedRetrievalIndex(
            scope=AuthorizedTenantGeneration(
                organization_id=1,
                workspace_id=2,
                knowledge_base_ids=(3,),
                generation_id=GENERATION_ID,
            ),
            space=write.space,
            materialization=write.materialization,
            collection_name=write.collection_name,
            assignment_epoch=1,
        )

        hits = await adapter.search(
            read,
            query_space=read.space,
            vector=[1.0, 0.0, 0.0],
            limit=10,
        )

        assert len(hits) == 1
        assert hits[0].payload["document_id"] == 10
        assert hits[0].payload["knowledge_base_id"] == 3
        assert (
            hits[0].payload["index_generation_id"]
            == str(GENERATION_ID)
        )
        assert (
            hits[0].payload["space_sha256"]
            == read.space.space_sha256
        )
        assert (
            hits[0].payload["materialization_sha256"]
            == read.materialization.materialization_sha256
        )

    finally:
        await client.close()


@pytest.mark.asyncio
async def test_equal_dimension_wrong_space_never_reaches_qdrant():
    index = read_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    wrong_space = space(
        model_id="equal-dimension-wrong-model"
    )

    assert wrong_space.dimensions == index.space.dimensions
    assert wrong_space.space_sha256 != index.space.space_sha256

    with pytest.raises(
        RetrievalCompatibilityError,
        match="embedding-space",
    ):
        await adapter.search(
            index,
            query_space=wrong_space,
            vector=[1.0, 0.0, 0.0],
            limit=3,
        )

    # Fail before collection inspection or search.
    assert client.calls == []


@pytest.mark.asyncio
async def test_existing_collection_repairs_only_missing_payload_indexes():
    index = write_index()
    client = FakeClient(index)

    # One valid index already exists; the remainder are missing.
    client.payload_schema["organization_id"] = SimpleNamespace(
        data_type=models.PayloadSchemaType.INTEGER
    )

    adapter = GenerationQdrantAdapter(client)

    created = await adapter.create_collection(index)

    assert created is False

    created_fields = {
        call[1]["field_name"]
        for call in client.calls
        if call[0] == "create_payload_index"
    }

    assert "organization_id" not in created_fields
    assert "workspace_id" in created_fields
    assert "index_generation_id" in created_fields
    assert "space_sha256" in created_fields

    # The completed fake schema must now satisfy the strict gate.
    await adapter.validate_payload_indexes(index)


@pytest.mark.asyncio
async def test_wrong_existing_payload_index_type_fails_before_repair():
    index = write_index()
    client = FakeClient(index)

    client.payload_schema["organization_id"] = SimpleNamespace(
        data_type=models.PayloadSchemaType.KEYWORD
    )

    adapter = GenerationQdrantAdapter(client)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="organization_id type mismatch",
    ):
        await adapter.create_collection(index)

    assert not any(
        call[0] == "create_payload_index"
        for call in client.calls
    )


@pytest.mark.asyncio
async def test_strict_payload_validation_rejects_missing_indexes():
    index = write_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    with pytest.raises(
        RetrievalCompatibilityError,
        match="required payload indexes are missing",
    ):
        await adapter.validate_payload_indexes(index)


@pytest.mark.asyncio
async def test_strict_payload_validation_accepts_complete_schema():
    index = write_index()
    client = FakeClient(index)
    adapter = GenerationQdrantAdapter(client)

    await adapter.create_collection(index)

    await adapter.validate_payload_indexes(index)
