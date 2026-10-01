from app.services.rag.chunker import chunk_text
from app.services.qdrant import QdrantService


class FakeEmbeddingService:
    async def embed_text(self, text):
        return [float(len(text))]

    async def embed_texts(self, texts):
        return [[float(len(text))] for text in texts]


def test_chunk_embedding_contract_and_no_trailing_overlap_chunk():
    chunks = chunk_text("one two three four five", 3, 1)
    assert chunks == ["one two three", "three four five"]
    assert len(__import__("asyncio").run(FakeEmbeddingService().embed_texts(chunks))) == 2


def test_embedding_service_can_be_replaced_without_downloading_model():
    service = FakeEmbeddingService()
    assert __import__("asyncio").run(service.embed_text("abc")) == [3.0]


def test_qdrant_point_ids_are_deterministic():
    assert QdrantService.point_id(10, 2) == QdrantService.point_id(10, 2)
    assert QdrantService.point_id(10, 2) != QdrantService.point_id(11, 2)
