"""CLI: ``python -m benchmarks.retrieval.run``."""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from app.core.config import get_settings
from app.services.evaluation.embedding_profiles import MINILM_BASELINE, MULTILINGUAL_E5_SMALL
from app.services.rag.embeddings import EmbeddingService
from benchmarks.retrieval.provenance import (
    discover_git_sha,
    normalize_runtime_build_sha,
    resolve_source_sha,
)
from benchmarks.retrieval.reporting import write_reports
from benchmarks.retrieval.runner import DeterministicFixtureEmbedder, RunConfiguration, run_benchmark_sync
from benchmarks.retrieval.schema import load_dataset


DEFAULT_DATASET = Path(__file__).parent / "datasets" / "v1" / "fixture.json"
KNOWN_MODEL_PROFILES = {
    MINILM_BASELINE.model_id: MINILM_BASELINE,
    MULTILINGUAL_E5_SMALL.model_id: MULTILINGUAL_E5_SMALL,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run an isolated retrieval-quality benchmark.")
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--embedding-model", default=MINILM_BASELINE.model_id)
    parser.add_argument("--revision", default=None, help="Pinned model revision; required for unregistered model IDs")
    parser.add_argument("--query-prefix", default=None)
    parser.add_argument("--passage-prefix", default=None)
    parser.add_argument("--output", type=Path, default=Path("artifacts/retrieval-benchmark/v1"))
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--chunk-size", type=int, default=None)
    parser.add_argument("--chunk-overlap", type=int, default=None)
    parser.add_argument(
        "--source-sha",
        default=None,
        help="Exact 40-hex commit SHA of the benchmark source; takes precedence over git discovery",
    )
    parser.add_argument(
        "--confirm-authoritative-corpus",
        action="store_true",
        help="Confirm the private corpus is human-labeled and representative before reporting real-world status",
    )
    parser.add_argument("--dry-run", action="store_true", help="Use deterministic stub vectors; not model-quality results")
    return parser


def resolve_embedding_options(
    model_id: str,
    *,
    revision: str | None = None,
    query_prefix: str | None = None,
    passage_prefix: str | None = None,
) -> tuple[str, str, str, str]:
    profile = KNOWN_MODEL_PROFILES.get(model_id)
    resolved_revision = revision or (profile.revision if profile else None)
    if not resolved_revision:
        raise ValueError("a pinned --revision is required for embedding models without a registered profile")
    resolved_query_prefix = query_prefix if query_prefix is not None else (profile.query_prefix if profile else "")
    resolved_passage_prefix = passage_prefix if passage_prefix is not None else (profile.passage_prefix if profile else "")
    return model_id, resolved_revision, resolved_query_prefix, resolved_passage_prefix


def _load_offline_model(model_id: str, revision: str):
    """Load a pre-provisioned snapshot only; all Hugging Face network access is disabled."""
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_DATASETS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    settings = get_settings()
    from huggingface_hub import snapshot_download
    from sentence_transformers import SentenceTransformer

    try:
        snapshot = Path(
            snapshot_download(
                repo_id=model_id,
                revision=revision,
                cache_dir=settings.embedding_cache_dir,
                local_files_only=True,
            )
        )
    except Exception as exc:
        raise RuntimeError("pinned embedding snapshot is not available locally; offline benchmark did not download it") from exc

    weight_files = [
        path
        for path in snapshot.rglob("*")
        if path.is_file() and path.suffix == ".safetensors"
    ]
    if not weight_files or not any(path.stat().st_size > 1_000_000 for path in weight_files):
        raise RuntimeError("local embedding snapshot contains no complete model weights; offline benchmark did not download them")

    model_started = time.perf_counter()
    model = SentenceTransformer(
        str(snapshot),
        device="cpu",
        local_files_only=True,
        trust_remote_code=False,
        model_kwargs={"use_safetensors": True, "local_files_only": True},
    )
    dimension = model.get_sentence_embedding_dimension()
    if not isinstance(dimension, int) or dimension <= 0:
        raise RuntimeError("embedding model did not report a valid vector dimension")
    return model, dimension, (time.perf_counter() - model_started) * 1000, str(model.device)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source_sha, source_sha_origin = resolve_source_sha(args.source_sha, discover_git_sha)
        dataset = load_dataset(args.dataset)
        if dataset.classification == "authoritative" and not args.confirm_authoritative_corpus:
            raise ValueError(
                "authoritative datasets require --confirm-authoritative-corpus after human/enterprise review"
            )
        model_id, revision, query_prefix, passage_prefix = resolve_embedding_options(
            args.embedding_model,
            revision=args.revision,
            query_prefix=args.query_prefix,
            passage_prefix=args.passage_prefix,
        )
        if args.top_k <= 0:
            raise ValueError("--top-k must be positive")
        settings = get_settings()
        chunk_size = args.chunk_size if args.chunk_size is not None else settings.chunk_size
        chunk_overlap = args.chunk_overlap if args.chunk_overlap is not None else settings.chunk_overlap
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk settings require size > 0 and 0 <= overlap < size")

        if args.dry_run:
            embedder = DeterministicFixtureEmbedder()
            embedding_dimension = embedder.dimension
            model_load_ms = None
            device = "deterministic-stub"
            execution_mode = "dry-run; synthetic hash vectors; not embedding-model quality"
        else:
            if model_id not in KNOWN_MODEL_PROFILES and not args.revision:
                raise ValueError("real runs require a pinned --revision for unregistered embedding models")
            model, embedding_dimension, model_load_ms, device = _load_offline_model(model_id, revision)
            embedder = EmbeddingService(model=model)
            execution_mode = "offline local model inference"

        report = run_benchmark_sync(
            RunConfiguration(
                dataset=dataset,
                embedding_model=("deterministic-hash-stub" if args.dry_run else model_id),
                embedding_revision=("not-applicable" if args.dry_run else revision),
                embedding_dimension=embedding_dimension,
                query_prefix="" if args.dry_run else query_prefix,
                passage_prefix="" if args.dry_run else passage_prefix,
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
                top_k=args.top_k,
                execution_mode=execution_mode,
                device=device,
                source_sha=source_sha,
                source_sha_origin=source_sha_origin,
                runtime_build_sha=normalize_runtime_build_sha(settings.build_sha),
                model_load_ms=model_load_ms,
            ),
            embedder,
        )
        json_path, markdown_path = write_reports(report, args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    print(f"JSON report: {json_path}")
    print(f"Markdown report: {markdown_path}")
    print(f"Benchmark source SHA: {source_sha or 'unavailable'} ({source_sha_origin})")
    print(f"Classification: {report['classification']}")
    print(f"Real-world benchmark status: {report['real_world_benchmark_status']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
