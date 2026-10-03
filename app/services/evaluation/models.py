"""Versioned, non-sensitive schemas for RAG quality evaluation."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_DATASET_VERSION = 1
SUPPORTED_CATEGORIES = {"general", "retrieval", "factual", "support", "policy", "technical"}


class EvaluationCase(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    category: str = Field(default="general", min_length=1, max_length=40)
    question: str = Field(min_length=1, max_length=12000)
    knowledge_base_ids: list[int] = Field(min_length=1, max_length=20)
    expected_documents: list[str] = Field(default_factory=list)
    expected_document_ids: list[int] = Field(default_factory=list, max_length=50)
    expected_facts: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, gt=0, le=50)

    @field_validator("id", "question")
    @classmethod
    def require_nonempty_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_CATEGORIES:
            supported = ", ".join(sorted(SUPPORTED_CATEGORIES))
            raise ValueError(f"must be one of: {supported}")
        return normalized

    @field_validator("knowledge_base_ids", "expected_document_ids")
    @classmethod
    def validate_positive_unique_ids(cls, value: list[int]) -> list[int]:
        if any(identifier <= 0 for identifier in value):
            raise ValueError("must contain only positive IDs")
        if len(set(value)) != len(value):
            raise ValueError("must not contain duplicates")
        return value

    @field_validator("expected_documents", "expected_facts")
    @classmethod
    def validate_expected_values(cls, value: list[str]) -> list[str]:
        normalized = [item.strip() for item in value]
        if any(not item for item in normalized):
            raise ValueError("must not contain blank strings")
        return normalized


class EvaluationDataset(BaseModel):
    version: Literal[SUPPORTED_DATASET_VERSION]
    name: str = Field(min_length=1, max_length=200)
    cases: list[EvaluationCase] = Field(min_length=1)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_unique_case_ids(self) -> "EvaluationDataset":
        case_ids = [case.id for case in self.cases]
        if len(set(case_ids)) != len(case_ids):
            raise ValueError("case IDs must be unique")
        return self


def dataset_fingerprint(dataset: EvaluationDataset) -> str:
    """Return a stable SHA-256 fingerprint of the complete validated dataset."""
    canonical_json = json.dumps(
        dataset.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


class RetrievedEvidence(BaseModel):
    """In-memory evidence. Its text is deliberately never serialized to results."""

    document: str = Field(min_length=1)
    score: float
    document_id: int | None = Field(default=None, gt=0)
    chunk_index: int | None = Field(default=None, ge=0)
    text: str | None = None


class RetrievalResult(BaseModel):
    evidence: list[RetrievedEvidence] = Field(default_factory=list)
    prompt: str | None = None
    embedding_latency_ms: float | None = Field(default=None, ge=0)
    retrieval_latency_ms: float | None = Field(default=None, ge=0)
    retrieval_scores: list[float] | None = None


class CaseLatencies(BaseModel):
    embedding_ms: float | None = Field(default=None, ge=0)
    retrieval_ms: float | None = Field(default=None, ge=0)
    generation_ms: float | None = Field(default=None, ge=0)
    total_ms: float = Field(ge=0)


class EvaluationCaseResult(BaseModel):
    case_id: str
    category: str
    knowledge_base_ids: list[int]
    effective_top_k: int | None = Field(default=None, gt=0)
    expected_documents: list[str]
    expected_document_ids: list[int] = Field(default_factory=list)
    returned_documents: list[str]
    # Preserve source ordering; ``null`` means legacy/fixture evidence lacked an ID.
    returned_document_ids: list[int | None] = Field(default_factory=list)
    returned_chunk_indexes: list[int | None] = Field(default_factory=list)
    source_hit: bool | None = None
    reciprocal_rank: float | None = None
    unexpected_sources: list[str] = Field(default_factory=list)
    no_source_returned: bool
    retrieved_source_count: int = Field(default=0, ge=0)
    retrieved_chunk_count: int = Field(default=0, ge=0)
    expected_fact_count: int
    facts_supported_by_sources: int
    fact_coverage: float | None = None
    answer_fact_groundedness: float | None = None
    # Safe output-size fallback; generated answer text is never persisted.
    generated_answer_char_count: int | None = Field(default=None, ge=0)
    top1_score: float | None = None
    top2_score: float | None = None
    top3_score: float | None = None
    score_gap_1_2: float | None = None
    score_gap_2_3: float | None = None
    score_ratio_2_1: float | None = None
    score_ratio_3_1: float | None = None
    score_ratio_3_2: float | None = None
    expected_source_rank: int | None = Field(default=None, gt=0)
    relevant_source_by_rank: list[bool] = Field(default_factory=list)
    fact_coverage_by_rank: list[float | None] = Field(default_factory=list)
    latencies: CaseLatencies


class EvaluationSummary(BaseModel):
    case_count: int
    hit_at_k: float | None = None
    mean_reciprocal_rank: float | None = None
    source_accuracy: float | None = None
    source_hit_count: int = 0
    unexpected_source_count: int = 0
    no_source_count: int = 0
    fact_coverage: float | None = None
    answer_fact_groundedness: float | None = None
    median_embedding_ms: float | None = None
    median_retrieval_ms: float | None = None
    median_generation_ms: float | None = None
    median_total_ms: float | None = None
    median_retrieved_source_count: float | None = None
    median_retrieved_chunk_count: float | None = None
    median_generated_answer_char_count: float | None = None


class EvaluationResult(BaseModel):
    schema_version: Literal[1] = 1
    dataset_version: Literal[SUPPORTED_DATASET_VERSION]
    dataset_name: str
    # Optional/defaulted fields keep persisted v0.5 pre-hardening results readable.
    dataset_fingerprint: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: Literal["fixture", "local"] = "fixture"
    models: dict[str, str | None] = Field(default_factory=dict)
    embedding_model: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    rag_top_k_default: int | None = Field(default=None, gt=0)
    # ``effective_top_k`` is set when every evaluated case used the same K.
    effective_top_k: int | None = Field(default=None, gt=0)
    top_k_override: int | None = Field(default=None, gt=0)
    application_version: str | None = None
    evaluation_mode: Literal["fixture", "local"] | None = None
    summary: EvaluationSummary
    cases: list[EvaluationCaseResult]
