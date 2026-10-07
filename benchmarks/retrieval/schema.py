"""Versioned, human-reviewable fixture corpus contracts."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


Language = Literal["tr", "en", "mixed"]
Category = Literal[
    "single_document_fact",
    "multi_document",
    "long_document",
    "semantic_distractors",
    "unanswerable",
]

_ID_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_CHUNK_ID_RE = re.compile(r"^(?P<document>[a-z][a-z0-9_-]{0,63})::chunk-(?P<index>[0-9]{4,})$")


class BenchmarkDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    language: Language
    text: str = Field(min_length=1, max_length=250_000)

    @field_validator("document_id")
    @classmethod
    def validate_document_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("document_id must be a stable lowercase benchmark identifier")
        return value

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("document text must not be blank")
        return value


class QueryCase(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query_id: str
    language: Language
    question: str = Field(min_length=1, max_length=12_000)
    expected_document_ids: list[str] = Field(default_factory=list)
    expected_chunk_ids: list[str] = Field(default_factory=list)
    categories: list[Category] = Field(min_length=1)
    answerable: bool
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("query_id")
    @classmethod
    def validate_query_id(cls, value: str) -> str:
        if not _ID_RE.fullmatch(value):
            raise ValueError("query_id must be a stable lowercase benchmark identifier")
        return value

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question must not be blank")
        return value.strip()

    @field_validator("expected_document_ids", "expected_chunk_ids", "categories")
    @classmethod
    def validate_unique_values(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            raise ValueError("labels and categories must not contain duplicates")
        return values

    @field_validator("expected_chunk_ids")
    @classmethod
    def validate_chunk_ids(cls, values: list[str]) -> list[str]:
        if any(not _CHUNK_ID_RE.fullmatch(value) for value in values):
            raise ValueError("expected_chunk_ids must use stable document::chunk-NNNN identifiers")
        return values

    @model_validator(mode="after")
    def validate_relevance(self) -> "QueryCase":
        if self.answerable:
            if not self.expected_document_ids:
                raise ValueError("answerable queries require expected document IDs")
            if "multi_document" in self.categories and len(self.expected_document_ids) < 2:
                raise ValueError("multi_document cases require at least two expected documents")
            if "single_document_fact" in self.categories and len(self.expected_document_ids) != 1:
                raise ValueError("single_document_fact cases require exactly one expected document")
            if "unanswerable" in self.categories:
                raise ValueError("answerable queries cannot use the unanswerable category")
            chunk_documents = {
                _CHUNK_ID_RE.fullmatch(chunk_id).group("document")
                for chunk_id in self.expected_chunk_ids
            }
            if not chunk_documents.issubset(set(self.expected_document_ids)):
                raise ValueError("expected chunk labels must belong to expected documents")
        else:
            if self.expected_document_ids or self.expected_chunk_ids:
                raise ValueError("unanswerable queries cannot declare relevant documents or chunks")
            if "unanswerable" not in self.categories:
                raise ValueError("unanswerable queries must include the unanswerable category")
        return self


class BenchmarkDataset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1]
    dataset_version: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=160)
    classification: Literal["fixture", "authoritative"]
    documents: list[BenchmarkDocument] = Field(min_length=1)
    queries: list[QueryCase] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_references(self) -> "BenchmarkDataset":
        document_ids = [document.document_id for document in self.documents]
        query_ids = [query.query_id for query in self.queries]
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("document IDs must be unique")
        if len(set(query_ids)) != len(query_ids):
            raise ValueError("query IDs must be unique")

        known_documents = set(document_ids)
        for query in self.queries:
            if not set(query.expected_document_ids).issubset(known_documents):
                raise ValueError(f"query {query.query_id} references an unknown document")
            if any(
                _CHUNK_ID_RE.fullmatch(chunk_id).group("document") not in known_documents
                for chunk_id in query.expected_chunk_ids
            ):
                raise ValueError(f"query {query.query_id} references an unknown chunk document")
        return self


def load_dataset(path: str | Path) -> BenchmarkDataset:
    """Load and fully validate a JSON benchmark dataset before model/vector work."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return BenchmarkDataset.model_validate(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("benchmark dataset could not be read as valid JSON") from exc


def dataset_fingerprint(dataset: BenchmarkDataset) -> str:
    """Hash validated content for paired-run identity without serializing its text."""
    canonical = json.dumps(
        dataset.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
