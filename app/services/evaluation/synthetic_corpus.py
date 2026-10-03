"""Canonical fingerprints for reusable, non-production evaluation corpora."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from app.services.evaluation.models import EvaluationDataset


def corpus_fingerprint(
    version: str,
    dataset: EvaluationDataset,
    documents: Sequence[Mapping[str, Any]],
) -> str:
    """Hash a validated dataset and its ordered document payloads canonically."""
    payload = {
        "version": version,
        "dataset": dataset.model_dump(mode="json"),
        "documents": list(documents),
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
