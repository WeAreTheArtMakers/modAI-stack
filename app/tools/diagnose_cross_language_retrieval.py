"""Offline deep-rank and tokenization diagnostics for synthetic retrieval corpora."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import numpy as np
from qdrant_client import QdrantClient, models

from app.core.config import get_settings
from app.services.evaluation.cross_language_diagnostics import (
    aggregate_cross_language_records,
    score_distribution,
    token_count_summary,
)
from app.services.evaluation.embedding_profiles import MINILM_BASELINE, MULTILINGUAL_E5_SMALL, MULTILINGUAL_E5_BASE
from app.services.evaluation.models import EvaluationDataset, dataset_fingerprint
from app.services.evaluation.synthetic_corpus import corpus_fingerprint
from app.services.rag.chunker import chunk_text
from app.tools.benchmark_embedding_profile import (
    _resolve_device,
    _validate_local_model_snapshot,
)


CANONICAL_VERSION = "compact-multilingual-v1"
CANONICAL_FINGERPRINT = "81d4546f3564171fd9f8a73ce82dd1f0a97e7ffde83660f9d972284f286f320b"
MIRROR_VERSION = "cross-language-mirror-v1"
MIRROR_FINGERPRINT = "95e188795dd5c493f10d1b6139559e9ffcd71c8dd5f6b8469865b833595e188c"
MAX_CROSS_LANGUAGE_RANK = 20


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("diagnostic input could not be read or parsed") from exc


def _load_inputs(dataset_path: Path, documents_path: Path) -> tuple[EvaluationDataset, str, list[dict[str, Any]]]:
    try:
        dataset = EvaluationDataset.model_validate(_read_json(dataset_path))
    except Exception as exc:
        raise ValueError("diagnostic dataset failed schema validation") from exc
    raw_documents = _read_json(documents_path)
    if not isinstance(raw_documents, dict) or not isinstance(raw_documents.get("documents"), list):
        raise ValueError("diagnostic documents must contain a documents array")
    version = raw_documents.get("corpus_version")
    if not isinstance(version, str) or not version.strip() or version != dataset.name:
        raise ValueError("dataset and documents must declare the same corpus version")
    documents = raw_documents["documents"]
    if not documents or any(not isinstance(item, dict) for item in documents):
        raise ValueError("diagnostic documents must be non-empty objects")
    return dataset, version, documents


def _direction(case: Any, documents_by_id: dict[int, dict[str, Any]]) -> str | None:
    if not case.expect_answer or not case.expected_document_ids:
        return None
    source_languages = {documents_by_id[item]["language"] for item in case.expected_document_ids}
    if len(source_languages) != 1:
        raise ValueError("cross-language diagnostics require one expected source language")
    source_language = next(iter(source_languages))
    if case.language == "tr" and source_language == "en":
        return "tr_query_to_en_document"
    if case.language == "en" and source_language == "tr":
        return "en_query_to_tr_document"
    return None


def _language_summary(values: list[float]) -> dict[str, float | int | None]:
    return score_distribution(values)


def _query_template(language: str, question: str) -> str:
    text = question.casefold()
    if language == "tr":
        first_token = re.findall(r"[^\W_]+", text, flags=re.UNICODE)[:1]
        if not first_token:
            return "empty"
        if re.fullmatch(r"20(?:24|25)", first_token[0]):
            return "year_context_opening"
        if first_token[0] in {"api", "http", "mfa"}:
            return "technical_abbreviation_opening"
        if first_token[0] in {"kaç", "ne", "nasıl", "hangi", "kim", "nerede"}:
            return "interrogative_opening"
        return "nominal_clause_opening"
    if text.startswith("what limit applies"):
        return "what_limit_applies"
    if text.startswith("what number"):
        return "what_number"
    if text.startswith("which "):
        return "which_selection"
    for marker, label in (
        ("how many", "quantity_how_many"),
        ("how long", "duration_how_long"),
        ("how often", "frequency_how_often"),
        ("when", "time_when"),
        ("within what", "deadline_within_what"),
        ("within how many", "deadline_within_how_many"),
        ("above what", "threshold_above_what"),
        ("what is", "value_what_is"),
    ):
        if marker in text:
            return label
    return "other"


def _shared_terminology_count(question: str, source_text: str) -> int:
    """Count shared non-numeric surface tokens; aggregate only, not a semantic score."""
    query_tokens = set(re.findall(r"[^\W_]+", question.casefold(), flags=re.UNICODE))
    source_tokens = set(re.findall(r"[^\W_]+", source_text.casefold(), flags=re.UNICODE))
    stop_tokens = {"a", "an", "and", "are", "at", "do", "for", "how", "in", "is", "of", "on", "the", "to", "what", "when", "with"}
    shared = query_tokens & source_tokens
    return sum(token not in stop_tokens and not token.isdecimal() for token in shared)


def audit_canonical_directionality(
    dataset: EvaluationDataset, documents: list[dict[str, Any]]
) -> dict[str, Any]:
    documents_by_id = {int(item["document_id"]): item for item in documents}
    directions: dict[str, list[Any]] = defaultdict(list)
    for case in dataset.cases:
        direction = _direction(case, documents_by_id)
        if direction:
            directions[direction].append(case)

    result: dict[str, Any] = {}
    for direction, cases in directions.items():
        sources = [documents_by_id[case.expected_document_ids[0]] for case in cases]
        case_type_counts = Counter(case.case_type for case in cases)
        source_lengths_chars = [len(item["text"]) for item in sources]
        source_lengths_words = [len(item["text"].split()) for item in sources]
        query_lengths_chars = [len(case.question) for case in cases]
        query_lengths_words = [len(case.question.split()) for case in cases]
        source_numeric_facts = sum(
            any(character.isdigit() for fact in case.expected_facts for character in fact)
            for case in cases
        )
        policy_version_cases = sum(
            bool(re.search(r"\b20(?:24|25)\b", source["text"]))
            for source in sources
        )
        query_numeric_cases = sum(bool(re.search(r"\d", case.question)) for case in cases)
        expected_families = [tuple(case.confusable_document_ids) for case in cases]
        shared_token_counts = [
            _shared_terminology_count(case.question, source["text"])
            for case, source in zip(cases, sources, strict=True)
        ]
        result[direction] = {
            "case_count": len(cases),
            "unique_expected_source_count": len({case.expected_document_ids[0] for case in cases}),
            "source_language_counts": dict(Counter(item["language"] for item in sources)),
            "case_type_counts": {name: case_type_counts.get(name, 0) for name in ("normal", "hard_negative", "no_answer")},
            "median_confusable_document_count": round(median([len(case.confusable_document_ids) for case in cases]), 2),
            "numeric_expected_fact_count": source_numeric_facts,
            "query_with_numeric_literal_count": query_numeric_cases,
            "expected_fact_character_length": _language_summary(
                [len(fact) for case in cases for fact in case.expected_facts]
            ),
            "policy_version_source_count": policy_version_cases,
            "query_references_policy_version_count": sum(
                bool(re.search(r"\b20(?:24|25)\b", case.question)) for case in cases
            ),
            "query_template_distribution": dict(Counter(
                _query_template(case.language, case.question) for case in cases
            )),
            "category_distribution": dict(Counter(case.category for case in cases)),
            "query_length_chars": _language_summary(query_lengths_chars),
            "query_length_words": _language_summary(query_lengths_words),
            "source_document_length_chars": _language_summary(source_lengths_chars),
            "source_document_length_words": _language_summary(source_lengths_words),
            "unique_confusable_set_count": len(set(expected_families)),
            "shared_non_numeric_query_source_terms": _language_summary(shared_token_counts),
            "cases_with_any_shared_non_numeric_query_source_term": sum(
                count > 0 for count in shared_token_counts
            ),
        }
    return result


def _token_count(tokenizer: Any, text: str) -> int:
    return len(tokenizer(text, add_special_tokens=True, truncation=False)["input_ids"])


def _tokenization_summary(
    tokenizer: Any,
    max_length: int,
    dataset: EvaluationDataset,
    chunks: list[dict[str, Any]],
    profile: Any,
) -> dict[str, Any]:
    query_counts: dict[str, list[int]] = {"en": [], "tr": []}
    document_counts: dict[str, list[int]] = {"en": [], "tr": []}
    for case in dataset.cases:
        if profile.query_prefix and case.question.startswith(profile.query_prefix):
            raise ValueError("query already contains the model prefix; refusing to double-prefix")
        query_counts[case.language].append(
            _token_count(tokenizer, profile.preprocess_query(case.question))
        )
    for chunk in chunks:
        if profile.passage_prefix and chunk["text"].startswith(profile.passage_prefix):
            raise ValueError("passage already contains the model prefix; refusing to double-prefix")
        document_counts[chunk["language"]].append(
            _token_count(tokenizer, profile.preprocess_passage(chunk["text"]))
        )
    return {
        "queries": {
            language: token_count_summary(values, max_length)
            for language, values in query_counts.items()
        },
        "documents": {
            language: token_count_summary(values, max_length)
            for language, values in document_counts.items()
        },
    }


def _dedupe_hits(hits: list[Any]) -> list[dict[str, Any]]:
    seen: set[int] = set()
    results: list[dict[str, Any]] = []
    for hit in hits:
        payload = hit.payload or {}
        document_id = int(payload["document_id"])
        if document_id in seen:
            continue
        seen.add(document_id)
        results.append({"document_id": document_id, "score": float(hit.score)})
    return results


def _hard_negative_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    both_in_top3 = [record for record in records if record["expected_rank"] and record["best_confusable_rank"]]
    return {
        "case_count": len(records),
        "expected_source_top3_case_count": sum(record["expected_rank"] is not None and record["expected_rank"] <= 3 for record in records),
        "expected_source_rank_buckets": {
            "1": sum(record["expected_rank"] == 1 for record in records),
            "2": sum(record["expected_rank"] == 2 for record in records),
            "3": sum(record["expected_rank"] == 3 for record in records),
            "miss_from_top3": sum(record["expected_rank"] is None or record["expected_rank"] > 3 for record in records),
        },
        "confusable_case_count_in_top3": sum(record["confusable_top3_count"] > 0 for record in records),
        "confusable_source_results_in_top3": sum(record["confusable_top3_count"] for record in records),
        "cases_with_both_expected_and_confusable_in_top3": len(both_in_top3),
        "expected_source_above_best_confusable": sum(record["expected_rank"] < record["best_confusable_rank"] for record in both_in_top3),
        "expected_source_below_best_confusable": sum(record["expected_rank"] > record["best_confusable_rank"] for record in both_in_top3),
    }


def _similarity_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    answerable = [record for record in records if record["expect_answer"]]
    no_answer = [record for record in records if not record["expect_answer"]]
    answerable_top1 = [record["top1_score"] for record in answerable if record["top1_score"] is not None]
    no_answer_top1 = [record["top1_score"] for record in no_answer if record["top1_score"] is not None]
    answerable_top3 = [score for record in answerable for score in record["top3_scores"]]
    no_answer_top3 = [score for record in no_answer for score in record["top3_scores"]]
    answerable_median = median(answerable_top1) if answerable_top1 else None
    no_answer_median = median(no_answer_top1) if no_answer_top1 else None
    return {
        "answerable": {
            "case_count": len(answerable),
            "top1_score": score_distribution(answerable_top1),
            "all_top3_scores": score_distribution(answerable_top3),
        },
        "no_answer": {
            "case_count": len(no_answer),
            "top1_score": score_distribution(no_answer_top1),
            "all_top3_scores": score_distribution(no_answer_top3),
        },
        "no_answer_minus_answerable_top1_median": (
            round(no_answer_median - answerable_median, 6)
            if no_answer_median is not None and answerable_median is not None else None
        ),
        "no_answer_minus_answerable_top3_score_median": (
            round(median(no_answer_top3) - median(answerable_top3), 6)
            if no_answer_top3 and answerable_top3 else None
        ),
    }


def _run_one_corpus(profile: Any, model: Any, dataset: EvaluationDataset, version: str,
                    documents: list[dict[str, Any]], chunk_size: int, chunk_overlap: int) -> dict[str, Any]:
    corpus_hash = corpus_fingerprint(version, dataset, documents)
    document_by_id = {int(item["document_id"]): item for item in documents}
    chunks: list[dict[str, Any]] = []
    for document in documents:
        for index, text in enumerate(chunk_text(document["text"], chunk_size, chunk_overlap)):
            chunks.append({
                "document_id": int(document["document_id"]),
                "filename": document["filename"],
                "language": document["language"],
                "knowledge_base_ids": sorted(set(document["knowledge_base_ids"])),
                "chunk_index": index,
                "text": text,
            })
    if not chunks:
        raise ValueError("diagnostic corpus produced no chunks")

    passage_inputs = []
    for chunk in chunks:
        if profile.passage_prefix and chunk["text"].startswith(profile.passage_prefix):
            raise ValueError("passage already contains the model prefix; refusing to double-prefix")
        passage_inputs.append(profile.preprocess_passage(chunk["text"]))
    document_vectors = model.encode(
        passage_inputs, batch_size=32, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
    )
    if document_vectors.shape != (len(chunks), profile.dimensions):
        raise ValueError("document embeddings have an unexpected shape")
    norms = np.linalg.norm(document_vectors, axis=1)
    if not np.isfinite(document_vectors).all() or not np.allclose(norms, 1.0, atol=1e-4):
        raise ValueError("document vectors must be finite and normalized")

    questions = []
    for case in dataset.cases:
        if profile.query_prefix and case.question.startswith(profile.query_prefix):
            raise ValueError("query already contains the model prefix; refusing to double-prefix")
        questions.append(profile.preprocess_query(case.question))
    query_vectors = model.encode(
        questions, batch_size=32, normalize_embeddings=True,
        convert_to_numpy=True, show_progress_bar=False,
    )
    if query_vectors.shape != (len(dataset.cases), profile.dimensions):
        raise ValueError("query embeddings have an unexpected shape")
    if not np.isfinite(query_vectors).all() or not np.allclose(
        np.linalg.norm(query_vectors, axis=1), 1.0, atol=1e-4
    ):
        raise ValueError("query vectors must be finite and normalized")

    tokenization = _tokenization_summary(
        model.tokenizer, int(model.max_seq_length), dataset, chunks, profile
    )
    direction_records: list[dict[str, Any]] = []
    hard_negative_records: list[dict[str, Any]] = []
    similarity_records: list[dict[str, Any]] = []
    cross_case_count = 0
    index_identity = json.dumps({
        "model_id": profile.model_id,
        "revision": profile.revision,
        "vector_space_identity": profile.vector_space_identity,
        "dimensions": profile.dimensions,
        "query_prefix": profile.query_prefix,
        "passage_prefix": profile.passage_prefix,
        "corpus_fingerprint": corpus_hash,
    }, sort_keys=True, separators=(",", ":"))
    index_hash = hashlib.sha256(index_identity.encode("utf-8")).hexdigest()
    collection_name = f"diag_{profile.vector_space_identity[:12]}_{corpus_hash[:12]}"

    with tempfile.TemporaryDirectory(prefix="modai-cross-language-diagnostic-") as temporary_dir:
        client = QdrantClient(path=str(Path(temporary_dir) / index_hash[:16]))
        client.create_collection(
            collection_name=collection_name,
            vectors_config=models.VectorParams(size=profile.dimensions, distance=models.Distance.COSINE),
        )
        client.upsert(
            collection_name=collection_name,
            points=[
                models.PointStruct(
                    id=str(uuid5(NAMESPACE_URL, f"{index_hash}:{chunk['document_id']}:{chunk['chunk_index']}")),
                    vector=vector.tolist(),
                    payload={key: chunk[key] for key in (
                        "document_id", "filename", "language", "knowledge_base_ids", "chunk_index", "text"
                    )},
                )
                for chunk, vector in zip(chunks, document_vectors, strict=True)
            ],
            wait=True,
        )

        for case, query_vector in zip(dataset.cases, query_vectors, strict=True):
            direction = _direction(case, document_by_id)
            search_limit = MAX_CROSS_LANGUAGE_RANK if direction else 3
            hits = client.search(
                collection_name=collection_name,
                query_vector=query_vector.tolist(),
                query_filter=models.Filter(must=[
                    models.FieldCondition(
                        key="knowledge_base_ids",
                        match=models.MatchAny(any=case.knowledge_base_ids),
                    )
                ]),
                limit=search_limit,
                with_payload=True,
            )
            ranked_hits = _dedupe_hits(hits)
            hit_ranks = {item["document_id"]: index for index, item in enumerate(ranked_hits, start=1)}
            top1_score = ranked_hits[0]["score"] if ranked_hits else None
            top3 = ranked_hits[:3]
            similarity_records.append({
                "expect_answer": case.expect_answer,
                "language": case.language,
                "top1_score": top1_score,
                "top3_scores": [item["score"] for item in top3],
            })

            if direction:
                cross_case_count += 1
                expected_vectors = [
                    vector for chunk, vector in zip(chunks, document_vectors, strict=True)
                    if chunk["document_id"] in case.expected_document_ids
                ]
                if not expected_vectors:
                    raise ValueError("cross-language case expected source has no indexed vector")
                expected_source_score = max(float(np.dot(query_vector, vector)) for vector in expected_vectors)
                expected_rank = next(
                    (hit_ranks[document_id] for document_id in case.expected_document_ids if document_id in hit_ranks),
                    None,
                )
                if expected_rank is not None and expected_rank <= 20:
                    retrieved_expected_score = next(
                        item["score"] for item in ranked_hits
                        if item["document_id"] in case.expected_document_ids
                    )
                    if abs(retrieved_expected_score - expected_source_score) > 2e-4:
                        raise ValueError("Qdrant cosine score disagrees with normalized local vector score")
                if top1_score is None:
                    raise ValueError("cross-language retrieval returned no top candidate")
                direction_records.append({
                    "direction": direction,
                    "rank": expected_rank,
                    "expected_source_score": expected_source_score,
                    "top1_score": top1_score,
                    "score_margin": top1_score - expected_source_score,
                })

            if case.case_type == "hard_negative":
                expected_rank = next(
                    (hit_ranks[document_id] for document_id in case.expected_document_ids if document_id in hit_ranks),
                    None,
                )
                confusable_ranks = [
                    hit_ranks[document_id] for document_id in case.confusable_document_ids
                    if document_id in hit_ranks and hit_ranks[document_id] <= 3
                ]
                hard_negative_records.append({
                    "expected_rank": expected_rank if expected_rank is not None and expected_rank <= 3 else None,
                    "best_confusable_rank": min(confusable_ranks) if confusable_ranks else None,
                    "confusable_top3_count": len(confusable_ranks),
                })
        client.close()

    if direction_records:
        direction_results = aggregate_cross_language_records(direction_records)
    else:
        direction_results = aggregate_cross_language_records([])
    hard_summary = _hard_negative_summary(hard_negative_records)
    return {
        "corpus_version": version,
        "corpus_fingerprint": corpus_hash,
        "dataset_fingerprint": dataset_fingerprint(dataset),
        "document_count": len(documents),
        "chunk_count": len(chunks),
        "case_count": len(dataset.cases),
        "top_k_production_reference": 3,
        "diagnostic_max_rank": MAX_CROSS_LANGUAGE_RANK,
        "index_identity": {
            "sha256": index_hash,
            "collection_name": collection_name,
            "model_id": profile.model_id,
            "revision": profile.revision,
            "vector_space_identity": profile.vector_space_identity,
            "corpus_fingerprint": corpus_hash,
            "distance": "cosine",
            "normalized_embeddings": True,
        },
        "tokenization": tokenization,
        "cross_language": direction_results,
        "hard_negative": hard_summary,
        "no_answer_similarity": _similarity_summary(similarity_records) if any(
            not case.expect_answer for case in dataset.cases
        ) else None,
    }


def run_diagnostics(minilm_path: Path, e5_path: Path, e5_base_path: Path, canonical_dataset_path: Path,
                    canonical_documents_path: Path, mirror_dataset_path: Path,
                    mirror_documents_path: Path, mirror_manifest_path: Path,
                    device_override: str | None = None) -> dict[str, Any]:
    os.environ.update({
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "HF_DATASETS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })

    canonical_dataset, canonical_version, canonical_documents = _load_inputs(
        canonical_dataset_path, canonical_documents_path
    )
    if canonical_version != CANONICAL_VERSION:
        raise ValueError("only compact-multilingual-v1 is accepted as the canonical diagnostic corpus")
    canonical_hash = corpus_fingerprint(canonical_version, canonical_dataset, canonical_documents)
    if canonical_hash != CANONICAL_FINGERPRINT:
        raise ValueError("canonical benchmark corpus fingerprint changed; refusing diagnostic run")
    cross_counts = Counter(
        _direction(case, {int(doc["document_id"]): doc for doc in canonical_documents})
        for case in canonical_dataset.cases
    )
    if cross_counts.get("tr_query_to_en_document", 0) != 22 or cross_counts.get("en_query_to_tr_document", 0) != 22:
        raise ValueError("canonical corpus cross-language case counts differ from expected 22 per direction")

    mirror_dataset, mirror_version, mirror_documents = _load_inputs(
        mirror_dataset_path, mirror_documents_path
    )
    if mirror_version != MIRROR_VERSION:
        raise ValueError("mirrored diagnostic set must use cross-language-mirror-v1")
    mirror_hash = corpus_fingerprint(mirror_version, mirror_dataset, mirror_documents)
    mirror_manifest = _read_json(mirror_manifest_path)
    if mirror_hash != MIRROR_FINGERPRINT or mirror_manifest.get("fingerprint_sha256") != mirror_hash:
        raise ValueError("mirrored corpus fingerprint does not match its manifest")
    mirror_direction_counts = Counter(
        _direction(case, {int(doc["document_id"]): doc for doc in mirror_documents})
        for case in mirror_dataset.cases
    )
    if mirror_direction_counts.get("tr_query_to_en_document", 0) != 20 or mirror_direction_counts.get("en_query_to_tr_document", 0) != 20:
        raise ValueError("mirrored diagnostic must contain 20 cases in each direction")

    try:
        import torch
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError("local PyTorch and SentenceTransformers are required; downloads are disabled") from exc

    settings = get_settings()
    if settings.embedding_model != MINILM_BASELINE.model_id or int(settings.rag_top_k) != 3:
        raise ValueError("production must remain on the MiniLM embedding and RAG_TOP_K=3 during diagnostics")
    chunk_size = int(settings.chunk_size)
    chunk_overlap = int(settings.chunk_overlap)
    if device_override not in {None, "cpu", "mps"}:
        raise ValueError("device must be cpu or mps")
    common_device = device_override or _resolve_device()[0]
    results: dict[str, Any] = {
        "schema_version": 1,
        "canonical_corpus": {
            "version": canonical_version,
            "fingerprint": canonical_hash,
            "document_count": len(canonical_documents),
            "case_count": len(canonical_dataset.cases),
        },
        "mirrored_corpus": {
            "version": mirror_version,
            "fingerprint": mirror_hash,
            "document_count": len(mirror_documents),
            "case_count": len(mirror_dataset.cases),
            "mirrored_fact_pair_count": int(mirror_manifest["mirrored_fact_pair_count"]),
        },
        "chunking": {"chunk_size": chunk_size, "chunk_overlap": chunk_overlap},
        "production_configuration": {
            "embedding_model": settings.embedding_model,
            "rag_top_k": int(settings.rag_top_k),
            "adaptive_retrieval_enabled": False,
            "reranker_enabled": False,
        },
        "device": {
            "torch_version": torch.__version__,
            "architecture": __import__("platform").machine(),
            "mps_built": bool(torch.backends.mps.is_built()),
            "mps_available": bool(torch.backends.mps.is_available()),
            "selected": common_device,
        },
        "normalization_contract": {
            "normalized_embeddings": True,
            "qdrant_distance": "cosine",
            "cross_model_vector_mixing": False,
        },
        "canonical_directionality_audit": audit_canonical_directionality(
            canonical_dataset, canonical_documents
        ),
        "models": {},
    }

    for profile, model_path, model_key in (
        (MINILM_BASELINE, minilm_path, "minilm"),
        (MULTILINGUAL_E5_SMALL, e5_path, "e5_small"),
        (MULTILINGUAL_E5_BASE, e5_base_path, "e5_base"),
    ):
        safetensors_hash = _validate_local_model_snapshot(profile, model_path)
        device, device_note = common_device, f"Explicit common diagnostic device: {common_device}."
        model = SentenceTransformer(
            str(model_path),
            device=device,
            local_files_only=True,
            trust_remote_code=False,
            model_kwargs={"use_safetensors": True, "local_files_only": True},
        )
        if int(model.max_seq_length) != profile.max_input_tokens:
            raise ValueError("model maximum sequence length differs from pinned profile metadata")
        model_result = {
            "profile": profile.safe_metadata(),
            "safetensors_sha256": safetensors_hash,
            "backend": "sentence-transformers / PyTorch",
            "device": str(model.device),
            "device_note": device_note,
            "offline_local_only": True,
            "canonical": _run_one_corpus(
                profile, model, canonical_dataset, canonical_version,
                canonical_documents, chunk_size, chunk_overlap,
            ),
            "mirrored": _run_one_corpus(
                profile, model, mirror_dataset, mirror_version,
                mirror_documents, chunk_size, chunk_overlap,
            ),
        }
        results["models"][model_key] = model_result
        del model
        gc.collect()
        if common_device == "mps":
            torch.mps.empty_cache()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minilm-model-path", type=Path, required=True)
    parser.add_argument("--e5-model-path", type=Path, required=True)
    parser.add_argument("--e5-base-model-path", type=Path, required=True)
    parser.add_argument("--device", choices=("cpu", "mps"), help="Pin one device across all models")
    parser.add_argument("--canonical-dataset", type=Path, required=True)
    parser.add_argument("--canonical-documents", type=Path, required=True)
    parser.add_argument("--mirror-dataset", type=Path, required=True)
    parser.add_argument("--mirror-documents", type=Path, required=True)
    parser.add_argument("--mirror-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="aggregate-only JSON output")
    args = parser.parse_args()
    result = run_diagnostics(
        args.minilm_model_path, args.e5_model_path, args.e5_base_model_path,
        args.canonical_dataset, args.canonical_documents,
        args.mirror_dataset, args.mirror_documents, args.mirror_manifest, args.device,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "canonical_fingerprint": result["canonical_corpus"]["fingerprint"],
        "mirror_fingerprint": result["mirrored_corpus"]["fingerprint"],
        "models": sorted(result["models"]),
        "output": "aggregate-only",
    }, sort_keys=True))


if __name__ == "__main__":
    main()
