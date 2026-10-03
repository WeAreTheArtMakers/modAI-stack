"""Run a local, authorized RAG quality evaluation without sending data to a cloud judge."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from app.core.security import decode_token
from app.services.evaluation.models import EvaluationCase, RetrievalResult, RetrievedEvidence
from app.services.evaluation.adaptive import AdaptivePolicy
from app.services.evaluation.runner import (
    AdaptiveContextRetriever,
    AuthorizedRagRetriever,
    EvaluationRunner,
    RerankedContextRetriever,
    load_dataset,
)
from app.services.evaluation.reranker import ARM64_ONNX_FILE, LocalCrossEncoderReranker
from app.services.llm.ollama import OllamaProvider


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate authorized local RAG retrieval and source quality.")
    parser.add_argument("--dataset", required=True, help="Versioned evaluation dataset JSON path")
    parser.add_argument("--mode", choices=("local", "fixture"), default="local")
    parser.add_argument("--fixture", help="Deterministic retrieval fixture JSON; required in fixture mode")
    parser.add_argument(
        "--access-token-env",
        default="MODAI_EVALUATION_ACCESS_TOKEN",
        help="Environment variable containing an access JWT for local mode (default: MODAI_EVALUATION_ACCESS_TOKEN)",
    )
    parser.add_argument("--generate", action="store_true", help="Also generate answers with the configured local Ollama model")
    parser.add_argument(
        "--top-k",
        type=int,
        help="Evaluation-only override for every case's top_k; does not change the dataset or production RAG_TOP_K",
    )
    parser.add_argument("--adaptive-policy", choices=("gap", "ratio", "three_tier"))
    parser.add_argument("--adaptive-threshold", type=float)
    parser.add_argument("--adaptive-second-threshold", type=float)
    parser.add_argument("--reranker-model", help="Explicitly provisioned local CrossEncoder model ID or path")
    parser.add_argument("--reranker-revision", help="Pinned local model revision (for reproducible cache-only loading)")
    parser.add_argument("--reranker-backend", choices=("torch", "onnx"), default="torch")
    parser.add_argument("--reranker-cache-dir", help="Local model cache directory; no model download is attempted")
    parser.add_argument("--candidate-pool-size", type=int, choices=(6, 8, 10))
    parser.add_argument("--json", action="store_true", help="Print the complete versioned result as JSON")
    parser.add_argument("--output", help="Write the complete versioned result to this JSON path")
    parser.add_argument("--min-hit-at-k", type=float)
    parser.add_argument("--min-source-accuracy", type=float)
    parser.add_argument("--min-fact-coverage", type=float)
    parser.add_argument("--max-median-total-ms", type=float)
    return parser.parse_args()


def _fixture_retriever(path: str):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Invalid retrieval fixture: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("Invalid retrieval fixture: expected an object keyed by case ID")

    async def retrieve(case: EvaluationCase) -> RetrievalResult:
        values = raw.get(case.id, [])
        if not isinstance(values, list):
            raise ValueError(f"Invalid retrieval fixture for case {case.id}")
        return RetrievalResult(evidence=[RetrievedEvidence.model_validate(value) for value in values])

    return retrieve


async def _run_local(
    dataset_path: str,
    token_env: str,
    generate: bool,
    top_k_override: int | None = None,
    adaptive_policy: AdaptivePolicy | None = None,
    adaptive_threshold: float | None = None,
    adaptive_second_threshold: float | None = None,
    reranker_model: str | None = None,
    reranker_revision: str | None = None,
    reranker_cache_dir: str | None = None,
    candidate_pool_size: int | None = None,
    reranker_backend: str = "torch",
):
    # Keep CLI fixture mode importable in test/air-gapped environments where a
    # production DATABASE_URL driver has intentionally not been installed.
    from app.db.session import SessionLocal

    token = os.environ.get(token_env)
    if not token:
        raise ValueError(f"Local mode requires an access JWT in {token_env}")
    user = decode_token(token)
    if user.get("type") != "access":
        raise ValueError("Local mode requires an access JWT")
    dataset = load_dataset(dataset_path)
    async with SessionLocal() as db:
        retriever = AuthorizedRagRetriever(db, user)
        if adaptive_policy is not None:
            retriever = AdaptiveContextRetriever(
                retriever,
                policy=adaptive_policy,
                threshold=adaptive_threshold,
                second_threshold=adaptive_second_threshold,
            )
        models = None
        if reranker_model is not None:
            provider = LocalCrossEncoderReranker(
                reranker_model,
                revision=reranker_revision,
                cache_dir=reranker_cache_dir,
                backend=reranker_backend,
            )
            # Load explicitly before timing cases; local_files_only=True forbids downloads.
            provider.load()
            retriever = RerankedContextRetriever(
                retriever,
                provider,
                candidate_pool_size=candidate_pool_size or 6,
                top_n=3,
            )
            models = {
                "reranker_model": reranker_model,
                "reranker_revision": reranker_revision,
                "reranker_backend": reranker_backend,
                "reranker_onnx_file": ARM64_ONNX_FILE if reranker_backend == "onnx" else None,
            }
        generator = None
        if generate:
            provider = OllamaProvider()

            async def generator(_case: EvaluationCase, result: RetrievalResult) -> str:
                if result.prompt is None:
                    raise RuntimeError("Local retrieval did not return a RAG prompt")
                return await provider.generate(result.prompt)

        return await EvaluationRunner(retriever, generator).run(
            dataset,
            mode="local",
            models=models,
            top_k_override=(3 if reranker_model is not None else top_k_override),
        )


async def _run_fixture(
    dataset_path: str,
    fixture_path: str | None,
    top_k_override: int | None = None,
    adaptive_policy: AdaptivePolicy | None = None,
    adaptive_threshold: float | None = None,
    adaptive_second_threshold: float | None = None,
    reranker_model: str | None = None,
    reranker_revision: str | None = None,
    reranker_cache_dir: str | None = None,
    candidate_pool_size: int | None = None,
    reranker_backend: str = "torch",
):
    if not fixture_path:
        raise ValueError("Fixture mode requires --fixture")
    dataset = load_dataset(dataset_path)
    retriever = _fixture_retriever(fixture_path)
    if adaptive_policy is not None:
        retriever = AdaptiveContextRetriever(
            retriever,
            policy=adaptive_policy,
            threshold=adaptive_threshold,
            second_threshold=adaptive_second_threshold,
        )
    models = None
    if reranker_model is not None:
        provider = LocalCrossEncoderReranker(
            reranker_model,
            revision=reranker_revision,
            cache_dir=reranker_cache_dir,
            backend=reranker_backend,
        )
        provider.load()
        retriever = RerankedContextRetriever(
            retriever,
            provider,
            candidate_pool_size=candidate_pool_size or 6,
            top_n=3,
        )
        models = {
            "reranker_model": reranker_model,
            "reranker_revision": reranker_revision,
            "reranker_backend": reranker_backend,
            "reranker_onnx_file": ARM64_ONNX_FILE if reranker_backend == "onnx" else None,
        }
    return await EvaluationRunner(retriever).run(
        dataset,
        mode="fixture",
        models=models,
        top_k_override=(3 if reranker_model is not None else top_k_override),
    )


def _validate_thresholds(args: argparse.Namespace, result) -> list[str]:
    checks = (
        ("min_hit_at_k", "hit_at_k", "minimum Hit@K"),
        ("min_source_accuracy", "source_accuracy", "minimum source accuracy"),
        ("min_fact_coverage", "fact_coverage", "minimum fact coverage"),
    )
    failures: list[str] = []
    for argument, metric, label in checks:
        expected = getattr(args, argument)
        actual = getattr(result.summary, metric)
        if expected is not None and (actual is None or actual < expected):
            failures.append(f"{label} threshold failed: actual={actual}, required={expected}")
    maximum = args.max_median_total_ms
    actual_latency = result.summary.median_total_ms
    if maximum is not None and (actual_latency is None or actual_latency > maximum):
        failures.append(f"maximum median total latency threshold failed: actual={actual_latency}, maximum={maximum}")
    return failures


def _validate_threshold_arguments(args: argparse.Namespace) -> None:
    for argument in ("min_hit_at_k", "min_source_accuracy", "min_fact_coverage"):
        value = getattr(args, argument)
        if value is not None and not 0 <= value <= 1:
            raise ValueError(f"{argument} must be between 0 and 1")
    if args.max_median_total_ms is not None and args.max_median_total_ms < 0:
        raise ValueError("max_median_total_ms must be non-negative")
    if getattr(args, "top_k", None) is not None and not 1 <= args.top_k <= 50:
        raise ValueError("top_k must be between 1 and 50")
    policy = getattr(args, "adaptive_policy", None)
    threshold = getattr(args, "adaptive_threshold", None)
    second_threshold = getattr(args, "adaptive_second_threshold", None)
    if policy is None and (threshold is not None or second_threshold is not None):
        raise ValueError("adaptive thresholds require --adaptive-policy")
    if policy is not None and threshold is None:
        raise ValueError("--adaptive-policy requires --adaptive-threshold")
    if policy == "three_tier" and second_threshold is None:
        raise ValueError("three_tier requires --adaptive-second-threshold")
    if policy != "three_tier" and second_threshold is not None:
        raise ValueError("--adaptive-second-threshold is only valid for three_tier")
    if policy is not None and getattr(args, "top_k", None) not in (None, 3):
        raise ValueError("adaptive context evaluation requires --top-k 3")
    reranker_model = getattr(args, "reranker_model", None)
    reranker_revision = getattr(args, "reranker_revision", None)
    reranker_backend = getattr(args, "reranker_backend", "torch")
    candidate_pool_size = getattr(args, "candidate_pool_size", None)
    if reranker_model is None and candidate_pool_size is not None:
        raise ValueError("--candidate-pool-size requires --reranker-model")
    if reranker_model is None and reranker_revision is not None:
        raise ValueError("--reranker-revision requires --reranker-model")
    if reranker_backend != "torch" and reranker_model is None:
        raise ValueError("--reranker-backend requires --reranker-model")
    if reranker_model is not None and candidate_pool_size is None:
        raise ValueError("--reranker-model requires --candidate-pool-size")
    if reranker_model is not None and policy is not None:
        raise ValueError("adaptive selection and reranking must be evaluated separately")
    if reranker_model is not None and getattr(args, "top_k", None) not in (None, 3):
        raise ValueError("reranker evaluation requires final --top-k 3")


def _print_summary(result) -> None:
    summary = result.summary
    print(
        f"{result.dataset_name}: cases={summary.case_count} hit_at_k={summary.hit_at_k} "
        f"mrr={summary.mean_reciprocal_rank} source_accuracy={summary.source_accuracy} "
        f"fact_coverage={summary.fact_coverage} median_reranker_ms={summary.median_reranker_ms} "
        f"median_total_ms={summary.median_total_ms}"
    )


def main() -> None:
    args = parse_args()
    try:
        _validate_threshold_arguments(args)
        result = asyncio.run(
            _run_fixture(
                args.dataset,
                args.fixture,
                3 if args.adaptive_policy else args.top_k,
                args.adaptive_policy,
                args.adaptive_threshold,
                args.adaptive_second_threshold,
                args.reranker_model,
                args.reranker_revision,
                args.reranker_cache_dir,
                args.candidate_pool_size,
                args.reranker_backend,
            )
            if args.mode == "fixture"
            else _run_local(
                args.dataset,
                args.access_token_env,
                args.generate,
                3 if args.adaptive_policy else args.top_k,
                args.adaptive_policy,
                args.adaptive_threshold,
                args.adaptive_second_threshold,
                args.reranker_model,
                args.reranker_revision,
                args.reranker_cache_dir,
                args.candidate_pool_size,
                args.reranker_backend,
            )
        )
        payload = result.model_dump(mode="json")
        if args.output:
            Path(args.output).write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            _print_summary(result)
        failures = _validate_thresholds(args, result)
        if failures:
            for failure in failures:
                print(f"THRESHOLD FAILED: {failure}")
            raise SystemExit(2)
    except ValueError as exc:
        raise SystemExit(f"Evaluation failed: {exc}") from exc


if __name__ == "__main__":
    main()
