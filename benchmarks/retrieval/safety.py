"""Fail-closed isolation and owned-collection lifecycle guards."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit


BENCHMARK_COLLECTION_PREFIX = "modai_benchmark_"
KNOWN_PRODUCTION_COLLECTIONS = frozenset({"rag_documents"})
_COLLECTION_RE = re.compile(r"^modai_benchmark_[a-f0-9]{16,32}$")


class BenchmarkSafetyError(RuntimeError):
    """Raised before a benchmark can touch a non-isolated vector target."""


def _canonical_endpoint(value: str) -> tuple[str, str, int, str]:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except (AttributeError, ValueError) as exc:
        raise BenchmarkSafetyError("Qdrant endpoint is invalid") from exc
    return parsed.scheme.lower(), parsed.hostname.lower().rstrip("."), port, parsed.path.rstrip("/")


def assert_endpoint_isolated(benchmark_endpoint: str, production_endpoint: str) -> None:
    """Reject the configured production Qdrant endpoint without exposing URLs."""
    if _canonical_endpoint(benchmark_endpoint) == _canonical_endpoint(production_endpoint):
        raise BenchmarkSafetyError("benchmark Qdrant endpoint must not be the production endpoint")


def validate_collection_name(name: str, production_names: set[str] | frozenset[str] = KNOWN_PRODUCTION_COLLECTIONS) -> None:
    if not _COLLECTION_RE.fullmatch(name):
        raise BenchmarkSafetyError("benchmark collection name must use the owned modai_benchmark_<run-id> form")
    if name in production_names:
        raise BenchmarkSafetyError("benchmark collection name matches a production collection")


@dataclass
class OwnedBenchmarkCollection:
    """A collection lease that can delete only a collection created by this run."""

    client: object
    name: str
    created_by_run: bool

    def delete(self) -> None:
        if not self.created_by_run:
            raise BenchmarkSafetyError("refusing to delete a collection not created by this benchmark run")
        validate_collection_name(self.name)
        self.client.delete_collection(collection_name=self.name)
        self.created_by_run = False


def create_owned_collection(client, *, name: str, dimensions: int) -> OwnedBenchmarkCollection:
    """Create only a new, clearly named benchmark collection on the supplied client."""
    validate_collection_name(name)
    if dimensions <= 0:
        raise ValueError("embedding dimensions must be positive")
    existing = {item.name for item in client.get_collections().collections}
    if name in existing:
        raise BenchmarkSafetyError("refusing to reuse a collection not owned by this benchmark run")
    from qdrant_client.http import models

    client.create_collection(
        collection_name=name,
        vectors_config=models.VectorParams(size=dimensions, distance=models.Distance.COSINE),
    )
    return OwnedBenchmarkCollection(client=client, name=name, created_by_run=True)
