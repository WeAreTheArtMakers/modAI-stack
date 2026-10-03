"""Run one pinned embedding profile against versioned data in isolated Qdrant.

The command is offline-only: callers must provision and pass a local model path.
Only aggregate metrics are written; raw cases, documents, and retrieved text stay
in memory and are never serialized.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import statistics
import sys
import tempfile
import time
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from app.core.config import get_settings
from app.services.evaluation.embedding_profiles import (
    MINILM_BASELINE,
    MULTILINGUAL_E5_SMALL,
    EmbeddingProfileSpec,
    EmbeddingSpaceGuard,
)
from app.services.evaluation.metrics import supported_fact_count
from app.services.evaluation.models import EvaluationDataset, dataset_fingerprint
from app.services.evaluation.synthetic_corpus import corpus_fingerprint
from app.services.rag.chunker import chunk_text

TOP_K = 3
E5_REQUIRED_SNAPSHOT_FILES = (
    "1_Pooling/config.json",
    "config.json",
    "modules.json",
    "sentence_bert_config.json",
    "sentencepiece.bpe.model",
    "special_tokens_map.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "model.safetensors",
)
E5_MODEL_SAFETENSORS_SHA256 = "1a55775f53449dac10a2bcbc312469fac40b96d53198c407081a831f81c98477"


def _read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("benchmark input could not be read or parsed") from exc


def _load_documents(path: Path) -> tuple[str, list[dict]]:
    raw = _read_json(path)
    if not isinstance(raw, dict) or not isinstance(raw.get("documents"), list):
        raise ValueError("documents input must be an object with a documents array")
    corpus_version = raw.get("corpus_version", "unspecified")
    if not isinstance(corpus_version, str) or not corpus_version.strip():
        raise ValueError("documents input must declare a non-empty corpus_version")
    documents: list[dict] = []
    seen: set[int] = set()
    for item in raw["documents"]:
        if not isinstance(item, dict):
            raise ValueError("each benchmark document must be an object")
        document_id = item.get("document_id")
        text = item.get("text")
        language = item.get("language")
        kb_ids = item.get("knowledge_base_ids")
        filename = item.get("filename", f"document-{document_id}")
        if not isinstance(document_id, int) or document_id <= 0 or document_id in seen:
            raise ValueError("benchmark document IDs must be unique positive integers")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("benchmark documents must contain non-empty text")
        if language not in {"en", "tr"}:
            raise ValueError("benchmark document language must be en or tr")
        if not isinstance(kb_ids, list) or not kb_ids or any(
            not isinstance(value, int) or value <= 0 for value in kb_ids
        ):
            raise ValueError("benchmark documents require positive Knowledge Base IDs")
        if not isinstance(filename, str) or not filename:
            raise ValueError("benchmark document filename must be non-empty")
        documents.append(
            {
                "document_id": document_id,
                "filename": filename,
                "language": language,
                "knowledge_base_ids": sorted(set(kb_ids)),
                "text": text,
            }
        )
        seen.add(document_id)
    if not documents:
        raise ValueError("benchmark documents must not be empty")
    return corpus_version, documents


def _load_dataset(path: Path) -> EvaluationDataset:
    raw = _read_json(path)
    try:
        dataset = EvaluationDataset.model_validate(raw)
    except Exception as exc:
        raise ValueError("benchmark dataset failed schema validation") from exc
    if any(case.top_k != TOP_K for case in dataset.cases):
        raise ValueError("embedding profile benchmark requires fixed K=3 in the dataset")
    return dataset


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 3) if values else None


def _peak_rss_bytes() -> int | None:
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except (AttributeError, OSError):
        return None
    return int(value if sys.platform == "darwin" else value * 1024)


def _resolve_device() -> tuple[str, str]:
    """Use MPS only when this exact PyTorch runtime reports it available."""
    try:
        import torch
    except ImportError:
        return "cpu", "PyTorch MPS availability could not be checked; CPU selected."
    if torch.backends.mps.is_built() and torch.backends.mps.is_available():
        return "mps", "Apple MPS is available in this PyTorch runtime."
    if not torch.backends.mps.is_built():
        return "cpu", "PyTorch was not built with MPS support; CPU selected."
    return "cpu", "MPS is built but unavailable in this runtime; CPU selected."


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as model_file:
        for block in iter(lambda: model_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _validate_local_model_snapshot(profile: EmbeddingProfileSpec, model_path: Path) -> str:
    if not model_path.is_dir():
        raise ValueError("model path is not a local directory; downloads are disabled")

    if profile.model_id == MULTILINGUAL_E5_SMALL.model_id:
        if profile.revision != MULTILINGUAL_E5_SMALL.revision:
            raise ValueError("E5 benchmark requires the exact pinned model revision")
        expected_directory_name = f"e5-small-{profile.revision}"
        required_files = E5_REQUIRED_SNAPSHOT_FILES
    elif profile.model_id == MINILM_BASELINE.model_id:
        if profile.revision != MINILM_BASELINE.revision:
            raise ValueError("MiniLM benchmark requires the exact pinned model revision")
        expected_directory_name = profile.revision
        required_files = ("model.safetensors",)
    else:
        raise ValueError("unsupported model identity for offline embedding benchmark")
    if model_path.name != expected_directory_name:
        raise ValueError("model path must use the exact pinned local snapshot directory name")

    missing_or_empty = [
        filename
        for filename in required_files
        if not (model_path / filename).is_file()
        or (model_path / filename).stat().st_size <= 0
    ]
    if missing_or_empty:
        raise ValueError(
            "pinned local model snapshot has missing or empty required files: "
            + ", ".join(missing_or_empty)
        )

    safetensors_sha256 = _sha256_file(model_path / "model.safetensors")
    if (
        profile.model_id == MULTILINGUAL_E5_SMALL.model_id
        and safetensors_sha256 != E5_MODEL_SAFETENSORS_SHA256
    ):
        raise ValueError("pinned E5 model.safetensors SHA-256 does not match the expected digest")
    return safetensors_sha256


def _group_metrics(records: list[dict]) -> dict:
    answerable = [record for record in records if record["answerable"]]
    if not answerable:
        return {
            "case_count": 0,
            "hit_at_3": None,
            "mrr": None,
            "rank_1_count": 0,
            "rank_2_count": 0,
            "rank_3_count": 0,
            "miss_count": 0,
            "source_accuracy": None,
            "fact_coverage": None,
        }
    ranks = [record["rank"] for record in answerable]
    hit_count = sum(rank is not None for rank in ranks)
    reciprocal_ranks = [1 / rank if rank is not None else 0.0 for rank in ranks]
    relevant = 0
    returned = 0
    covered = 0
    facts = 0
    for record in answerable:
        expected = record["expected_ids"]
        retrieved = record["retrieved_ids"]
        relevant += sum(document_id in expected for document_id in retrieved)
        returned += len(retrieved)
        covered += record["covered_facts"]
        facts += record["fact_count"]
    return {
        "case_count": len(answerable),
        "hit_at_3": round(hit_count / len(answerable), 4),
        "mrr": round(sum(reciprocal_ranks) / len(answerable), 4),
        "rank_1_count": sum(rank == 1 for rank in ranks),
        "rank_2_count": sum(rank == 2 for rank in ranks),
        "rank_3_count": sum(rank == 3 for rank in ranks),
        "miss_count": sum(rank is None for rank in ranks),
        "source_accuracy": round(relevant / returned, 4) if returned else None,
        "fact_coverage": round(covered / facts, 4) if facts else None,
    }


def _validate_profile_preprocessing(profile: EmbeddingProfileSpec) -> None:
    if profile.model_id == "intfloat/multilingual-e5-small":
        if profile.query_prefix != "query: " or profile.passage_prefix != "passage: ":
            raise ValueError("E5 benchmark runs require the documented query and passage prefixes")
    elif profile.model_id == "sentence-transformers/all-MiniLM-L6-v2":
        if profile.query_prefix or profile.passage_prefix:
            raise ValueError("MiniLM benchmark inputs must remain unprefixed")


def _run(profile: EmbeddingProfileSpec, model_path: Path, dataset_path: Path, documents_path: Path) -> dict:
    _validate_profile_preprocessing(profile)
    safetensors_sha256 = _validate_local_model_snapshot(profile, model_path)
    dataset = _load_dataset(dataset_path)
    corpus_version, documents = _load_documents(documents_path)
    if corpus_version != "unspecified" and dataset.name != corpus_version:
        raise ValueError("dataset name and document corpus_version do not match")
    full_corpus_fingerprint = corpus_fingerprint(corpus_version, dataset, documents)
    by_document_id = {document["document_id"]: document for document in documents}

    for case in dataset.cases:
        for document_id in (*case.expected_document_ids, *case.confusable_document_ids):
            document = by_document_id.get(document_id)
            if document is None:
                raise ValueError("an expected or confusable document is missing from the corpus")
            if not set(document["knowledge_base_ids"]).intersection(case.knowledge_base_ids):
                raise ValueError("an expected or confusable source is outside the case Knowledge Base scope")

    device, device_note = _resolve_device()
    model_load_started = time.perf_counter()
    try:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(
            str(model_path),
            device=device,
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"use_safetensors": True, "local_files_only": True},
        )
    except Exception as exc:
        raise ValueError("the pinned local embedding model could not be loaded offline") from exc
    model_load_ms = (time.perf_counter() - model_load_started) * 1000

    actual_max_length = int(model.max_seq_length)
    if actual_max_length != profile.max_input_tokens:
        raise ValueError("local model maximum input length does not match pinned profile metadata")
    space_guard = EmbeddingSpaceGuard(profile)
    smoke_vector = model.encode(
        [profile.preprocess_query("offline embedding dimension check")],
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )[0]
    space_guard.validate_vector(profile, smoke_vector)

    settings = get_settings()
    chunk_size = int(settings.chunk_size)
    chunk_overlap = int(settings.chunk_overlap)
    chunks: list[dict] = []
    for document in documents:
        for chunk_index, text in enumerate(chunk_text(document["text"], chunk_size, chunk_overlap)):
            chunks.append(
                {
                    "document_id": document["document_id"],
                    "filename": document["filename"],
                    "language": document["language"],
                    "knowledge_base_ids": document["knowledge_base_ids"],
                    "chunk_index": chunk_index,
                    "text": text,
                }
            )
    if not chunks:
        raise ValueError("benchmark corpus produced no chunks")

    index_started = time.perf_counter()
    document_embed_started = time.perf_counter()
    document_vectors = model.encode(
        [profile.preprocess_passage(item["text"]) for item in chunks],
        batch_size=32,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    document_embedding_ms = (time.perf_counter() - document_embed_started) * 1000
    if len(document_vectors) != len(chunks):
        raise ValueError("embedding model returned an unexpected number of document vectors")
    space_guard.validate_vectors(profile, document_vectors)

    records: list[dict] = []
    query_embedding_latencies: list[float] = []
    retrieval_latencies: list[float] = []
    no_answer_records: list[dict] = []
    hard_negative_records: list[dict] = []
    by_language: dict[str, list[dict]] = {"en": [], "tr": []}
    cross_language: dict[str, list[dict]] = {"tr_query_to_en_document": [], "en_query_to_tr_document": []}
    no_answer_by_language: dict[str, list[dict]] = {"en": [], "tr": []}

    with tempfile.TemporaryDirectory(prefix="modai-embedding-benchmark-") as temporary_dir:
        qdrant_path = Path(temporary_dir) / profile.collection_name
        client = QdrantClient(path=str(qdrant_path))
        collection_name = profile.collection_name
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=profile.dimensions, distance=models.Distance.COSINE),
        )

        qdrant_started = time.perf_counter()
        points = [
            models.PointStruct(
                id=str(uuid5(NAMESPACE_URL, f"{profile.vector_space_identity}:{item['document_id']}:{item['chunk_index']}")),
                vector=vector.tolist(),
                payload={key: item[key] for key in (
                    "document_id", "filename", "language", "knowledge_base_ids", "chunk_index", "text"
                )},
            )
            for item, vector in zip(chunks, document_vectors, strict=True)
        ]
        client.upsert(collection_name=collection_name, points=points, wait=True)
        qdrant_upsert_ms = (time.perf_counter() - qdrant_started) * 1000
        index_wall_ms = (time.perf_counter() - index_started) * 1000

        for case in dataset.cases:
            if case.case_type == "authorization_negative":
                # Authorization probes must be denied before any isolated
                # retrieval call. Their security result belongs to the
                # existing authorization evaluation, not this model comparison.
                records.append(
                    {
                        "answerable": False,
                        "rank": None,
                        "expected_ids": set(),
                        "retrieved_ids": [],
                        "covered_facts": 0,
                        "fact_count": 0,
                        "payloads": [],
                        "confusable_ids": set(),
                        "query_language": case.language,
                    }
                )
                continue
            query_started = time.perf_counter()
            query_vector = model.encode(
                [profile.preprocess_query(case.question)],
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )[0]
            query_ms = (time.perf_counter() - query_started) * 1000
            space_guard.validate_vector(profile, query_vector)
            query_embedding_latencies.append(query_ms)

            retrieval_started = time.perf_counter()
            hits = client.search(
                collection_name=collection_name,
                query_vector=query_vector.tolist(),
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="knowledge_base_ids",
                            match=models.MatchAny(any=case.knowledge_base_ids),
                        )
                    ]
                ),
                limit=TOP_K,
                with_payload=True,
            )
            retrieval_ms = (time.perf_counter() - retrieval_started) * 1000
            retrieval_latencies.append(retrieval_ms)
            payloads = [hit.payload or {} for hit in hits]
            retrieved_ids = [int(payload["document_id"]) for payload in payloads]
            expected_ids = set(case.expected_document_ids)
            rank = next(
                (index for index, document_id in enumerate(retrieved_ids, start=1) if document_id in expected_ids),
                None,
            ) if case.expect_answer else None
            text_values = [payload.get("text", "") for payload in payloads]
            supported = supported_fact_count(case.expected_facts, text_values) if case.expect_answer else 0
            record = {
                "answerable": case.expect_answer,
                "rank": rank,
                "expected_ids": expected_ids,
                "retrieved_ids": retrieved_ids,
                "covered_facts": supported,
                "fact_count": len(case.expected_facts),
                "payloads": payloads,
                "confusable_ids": set(case.confusable_document_ids),
                "query_language": case.language,
            }
            records.append(record)
            if case.case_type == "no_answer":
                no_answer_records.append(record)
                no_answer_by_language[case.language].append(record)
            elif case.expect_answer:
                by_language[case.language].append(record)
                if case.case_type == "hard_negative":
                    hard_negative_records.append(record)

            if case.expect_answer and expected_ids:
                expected_languages = {by_document_id[identifier]["language"] for identifier in expected_ids}
                if len(expected_languages) == 1:
                    expected_language = next(iter(expected_languages))
                    if case.language == "tr" and expected_language == "en":
                        cross_language["tr_query_to_en_document"].append(record)
                    elif case.language == "en" and expected_language == "tr":
                        cross_language["en_query_to_tr_document"].append(record)

        client.close()
        qdrant_storage_bytes = _directory_size(qdrant_path)

    all_metrics = _group_metrics(records)
    hard_metrics = _group_metrics(hard_negative_records)
    language_metrics = {language: _group_metrics(values) for language, values in by_language.items()}
    cross_metrics = {direction: _group_metrics(values) for direction, values in cross_language.items()}
    confusable_documents_in_hard_negative = sum(
        sum(document_id in record["confusable_ids"] for document_id in record["retrieved_ids"])
        for record in hard_negative_records
    )
    report = {
        "schema_version": 1,
        "profile": profile.safe_metadata(),
        "model_artifacts": {"safetensors_sha256": safetensors_sha256},
        "inference": {
            "backend": "sentence-transformers / PyTorch",
            "device": str(model.device),
            "device_note": device_note,
            "offline_only": True,
            "dimension_smoke_test": len(smoke_vector) == profile.dimensions,
        },
        "corpus_version": corpus_version,
        "corpus_fingerprint": full_corpus_fingerprint,
        "dataset_fingerprint": dataset_fingerprint(dataset),
        "case_count": len(dataset.cases),
        "authorization_probe_case_count": sum(
            case.case_type == "authorization_negative" for case in dataset.cases
        ),
        "authorization_probes_excluded_from_embedding_retrieval": True,
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "top_k": TOP_K,
        "reranker_enabled": False,
        "adaptive_retrieval_enabled": False,
        "hybrid_retrieval_enabled": False,
        "overall": all_metrics,
        "by_query_language": language_metrics,
        "cross_language": cross_metrics,
        "hard_negative": {
            **hard_metrics,
            "confusable_document_hits_in_top_3": confusable_documents_in_hard_negative,
        },
        "no_answer": {
            "case_count": len(no_answer_records),
            "confusable_case_count": sum(
                bool(set(record["retrieved_ids"]) & record["confusable_ids"])
                for record in no_answer_records
            ),
            "confusable_source_count": sum(
                len(set(record["retrieved_ids"]) & record["confusable_ids"])
                for record in no_answer_records
            ),
            "by_query_language": {
                language: {
                    "case_count": len(language_records),
                    "confusable_case_count": sum(
                        bool(set(record["retrieved_ids"]) & record["confusable_ids"])
                        for record in language_records
                    ),
                    "confusable_source_count": sum(
                        len(set(record["retrieved_ids"]) & record["confusable_ids"])
                        for record in language_records
                    ),
                }
                for language, language_records in no_answer_by_language.items()
            },
        },
        "latency_ms": {
            "model_load": round(model_load_ms, 3),
            "query_embedding_median": _median(query_embedding_latencies),
            "query_embedding_p95": round(sorted(query_embedding_latencies)[int(0.95 * (len(query_embedding_latencies) - 1))], 3) if query_embedding_latencies else None,
            "retrieval_median": _median(retrieval_latencies),
            "total_retrieval_median": _median([a + b for a, b in zip(query_embedding_latencies, retrieval_latencies, strict=True)]),
            "document_embedding_total": round(document_embedding_ms, 3),
            "document_chunks_per_second": round(len(chunks) / (document_embedding_ms / 1000), 3) if document_embedding_ms else None,
            "qdrant_upsert_total": round(qdrant_upsert_ms, 3),
            "indexing_wall_total": round(index_wall_ms, 3),
        },
        "storage": {
            "vector_count": len(chunks),
            "vector_dimension": profile.dimensions,
            "raw_float32_vector_bytes": len(chunks) * profile.dimensions * 4,
            "isolated_qdrant_directory_bytes": qdrant_storage_bytes,
        },
        "peak_process_rss_bytes": _peak_rss_bytes(),
        "limitations": [
            "Synthetic/private corpus metrics do not establish customer workload quality.",
            "Peak RSS is a process-level high-water mark, not model-only memory.",
            "Qdrant local directory size is an isolated local index measurement, not production storage overhead.",
        ],
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("minilm", "e5-small"), required=True)
    parser.add_argument("--model-path", type=Path, required=True, help="Already-provisioned local model directory; never downloads")
    parser.add_argument("--dataset", type=Path, required=True, help="Versioned EvaluationDataset JSON")
    parser.add_argument("--documents", type=Path, required=True, help="Document JSON with text, IDs, KB scopes, and languages")
    parser.add_argument("--output", type=Path, required=True, help="Aggregate-only JSON result path")
    args = parser.parse_args()
    profile = MINILM_BASELINE if args.profile == "minilm" else MULTILINGUAL_E5_SMALL
    result = _run(profile, args.model_path, args.dataset, args.documents)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"profile_id": profile.profile_id, "dataset_fingerprint": result["dataset_fingerprint"], "output": "aggregate-only"}, sort_keys=True))


if __name__ == "__main__":
    main()
