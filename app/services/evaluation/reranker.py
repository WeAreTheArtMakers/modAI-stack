"""Experimental local cross-encoder interfaces for evaluation-only reranking."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.services.evaluation.models import RetrievedEvidence


class RerankerEvaluationError(RuntimeError):
    """A reranker could not produce a valid result; evaluation must stop."""


ARM64_ONNX_FILE = "onnx/model_qint8_arm64.onnx"
SUPPORTED_BACKENDS = {"torch", "onnx"}


@dataclass(frozen=True)
class ScoredCandidate:
    evidence: RetrievedEvidence
    score: float


class RerankerProvider(Protocol):
    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedEvidence],
        top_n: int,
    ) -> list[ScoredCandidate]: ...


class LocalCrossEncoderReranker:
    """Load a provisioned Sentence Transformers CrossEncoder without network access."""

    def __init__(
        self,
        model_name: str,
        *,
        revision: str | None = None,
        cache_dir: str | Path | None = None,
        device: str | None = None,
        backend: str = "torch",
        onnx_file_name: str | None = None,
        model=None,
    ):
        if not model_name.strip():
            raise ValueError("model_name must not be blank")
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"backend must be one of: {', '.join(sorted(SUPPORTED_BACKENDS))}")
        if backend == "onnx" and onnx_file_name is not None and not onnx_file_name.strip():
            raise ValueError("onnx_file_name must not be blank")
        if backend == "torch" and onnx_file_name is not None:
            raise ValueError("onnx_file_name is only valid for the ONNX backend")
        self.model_name = model_name
        self.revision = revision
        self.cache_dir = str(cache_dir) if cache_dir is not None else None
        self.device = device
        self.backend = backend
        self.onnx_file_name = onnx_file_name or (ARM64_ONNX_FILE if backend == "onnx" else None)
        self._model = model

    def load(self) -> None:
        """Explicitly load already provisioned weights; never downloads a model."""
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder

            options = {
                "revision": self.revision,
                "cache_folder": self.cache_dir,
                "device": self.device,
                "local_files_only": True,
                "trust_remote_code": False,
            }
            if self.backend == "onnx":
                options.update(
                    backend="onnx",
                    model_kwargs={
                        "file_name": self.onnx_file_name,
                        "provider": "CPUExecutionProvider",
                        "export": False,
                    },
                )
            self._model = CrossEncoder(self.model_name, **options)
        except TypeError as exc:
            if self.backend == "onnx":
                raise RerankerEvaluationError(
                    "ONNX reranking requires the optional requirements-evaluation-onnx.txt dependencies"
                ) from exc
            raise RerankerEvaluationError(
                f"Local reranker unavailable for evaluation: {self.model_name}; "
                "provision compatible weights explicitly before running this experiment"
            ) from exc
        except Exception as exc:
            raise RerankerEvaluationError(
                f"Local reranker unavailable for evaluation: {self.model_name}; "
                "provision compatible weights explicitly before running this experiment"
            ) from exc

    async def rerank(
        self,
        query: str,
        candidates: Sequence[RetrievedEvidence],
        top_n: int,
    ) -> list[ScoredCandidate]:
        if top_n < 0:
            raise ValueError("top_n must be non-negative")
        if not candidates or top_n == 0:
            return []
        if not query.strip():
            raise ValueError("query must not be blank")
        if any(not item.text for item in candidates):
            raise RerankerEvaluationError("reranking requires candidate text")
        return await asyncio.to_thread(self._rerank_sync, query, candidates, top_n)

    def _rerank_sync(
        self,
        query: str,
        candidates: Sequence[RetrievedEvidence],
        top_n: int,
    ) -> list[ScoredCandidate]:
        self.load()
        pairs = [(query, item.text or "") for item in candidates]
        try:
            raw_scores = self._model.predict(pairs, show_progress_bar=False)
            if hasattr(raw_scores, "tolist"):
                raw_scores = raw_scores.tolist()
            scores = [float(value) for value in raw_scores]
        except Exception as exc:
            raise RerankerEvaluationError("local reranker inference failed") from exc
        if len(scores) != len(candidates) or any(not math.isfinite(value) for value in scores):
            raise RerankerEvaluationError("local reranker returned invalid scores")

        ranked = [
            ScoredCandidate(evidence=item, score=score)
            for item, score in zip(candidates, scores, strict=True)
        ]
        # Python sorting is stable, so equal scores preserve vector-search order.
        ranked.sort(key=lambda candidate: -candidate.score)
        return ranked[:top_n]
