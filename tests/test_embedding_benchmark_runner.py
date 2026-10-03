import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.services.evaluation.embedding_profiles import MINILM_BASELINE
from app.services.evaluation.models import EvaluationCase, EvaluationDataset
from app.tools import benchmark_embedding_profile as benchmark


def test_runner_uses_ephemeral_profile_isolated_qdrant_and_serializes_aggregates_only(
    tmp_path, monkeypatch
):
    private_question = "Synthetic sentinel question must never be serialized"
    private_document_text = "Synthetic sentinel document sentence contains 42 fictional units."
    dataset = EvaluationDataset(
        version=1,
        name="runner-test-v1",
        cases=[
            EvaluationCase(
                id="answerable",
                category="general",
                question=private_question,
                knowledge_base_ids=[1],
                language="en",
                expected_document_ids=[1],
                expected_facts=["42 fictional units"],
                top_k=3,
            ),
            EvaluationCase(
                id="no-answer",
                category="general",
                question="A second synthetic question",
                knowledge_base_ids=[1],
                case_type="no_answer",
                language="en",
                expect_answer=False,
                confusable_document_ids=[2],
                top_k=3,
            ),
        ],
    )
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(
        json.dumps(dataset.model_dump(mode="json")), encoding="utf-8"
    )
    documents_path = tmp_path / "documents.json"
    documents_path.write_text(
        json.dumps(
            {
                "corpus_version": "runner-test-v1",
                "documents": [
                    {
                        "document_id": 1,
                        "filename": "synthetic-answer.md",
                        "language": "en",
                        "knowledge_base_ids": [1],
                        "text": private_document_text,
                    },
                    {
                        "document_id": 2,
                        "filename": "synthetic-confusable.md",
                        "language": "en",
                        "knowledge_base_ids": [1],
                        "text": "Another synthetic confusable policy.",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    model_path = tmp_path / MINILM_BASELINE.revision
    model_path.mkdir()
    (model_path / "model.safetensors").write_bytes(b"test-only non-empty placeholder")

    class FakeModel:
        max_seq_length = MINILM_BASELINE.max_input_tokens
        device = "cpu"

        def encode(self, values, **kwargs):
            return np.zeros((len(values), MINILM_BASELINE.dimensions), dtype=np.float32)

    constructor_calls = []

    def fake_sentence_transformer(*args, **kwargs):
        constructor_calls.append((args, kwargs))
        return FakeModel()

    monkeypatch.setitem(
        __import__("sys").modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=fake_sentence_transformer),
    )
    monkeypatch.setattr(benchmark, "_resolve_device", lambda: ("cpu", "test CPU"))
    monkeypatch.setattr(
        benchmark,
        "get_settings",
        lambda: SimpleNamespace(chunk_size=700, chunk_overlap=100, qdrant_url="http://production.invalid"),
    )
    clients = []

    class FakeQdrantClient:
        def __init__(self, *, path):
            assert path
            assert "production.invalid" not in path
            self.path = Path(path)
            self.points = []
            self.collection_name = None
            clients.append(self)

        def create_collection(self, *, collection_name, vectors_config):
            self.collection_name = collection_name

        def upsert(self, *, collection_name, points, wait):
            assert collection_name == self.collection_name
            self.points = points

        def search(self, *, collection_name, query_vector, query_filter, limit, with_payload):
            assert collection_name == self.collection_name
            assert limit == 3
            return [SimpleNamespace(payload=point.payload) for point in self.points[:limit]]

        def close(self):
            return None

    monkeypatch.setattr(benchmark, "QdrantClient", FakeQdrantClient)
    report = benchmark._run(
        MINILM_BASELINE, model_path, dataset_path, documents_path
    )

    serialized = json.dumps(report, sort_keys=True)
    assert private_question not in serialized
    assert private_document_text not in serialized
    assert str(model_path) not in serialized
    assert report["top_k"] == 3
    assert report["corpus_version"] == "runner-test-v1"
    assert report["inference"]["offline_only"] is True
    assert report["inference"]["dimension_smoke_test"] is True
    assert report["index_identity"]["collection_name"] == clients[0].collection_name
    assert report["index_identity"]["corpus_fingerprint"] == report["corpus_fingerprint"]
    assert report["index_identity"]["vector_space_identity"] == MINILM_BASELINE.vector_space_identity
    assert report["no_answer"]["confusable_case_count"] == 1
    assert report["no_answer"]["confusable_source_count"] == 1
    assert len(clients) == 1
    assert clients[0].collection_name.startswith("embedding_benchmark_")
    assert clients[0].path.name == MINILM_BASELINE.collection_name
    assert len(constructor_calls) == 1
    args, kwargs = constructor_calls[0]
    assert args == (str(model_path),)
    assert kwargs["local_files_only"] is True
    assert kwargs["trust_remote_code"] is False
    assert kwargs["model_kwargs"] == {
        "use_safetensors": True,
        "local_files_only": True,
    }
